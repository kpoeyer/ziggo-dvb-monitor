import asyncio
import contextlib
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .config import settings
from .db import Store
from .scanner import Scanner

app = FastAPI(title="Ziggo DVB-C Monitor", version="0.1.0")
store = Store(settings.database)
scanner = Scanner(settings)
scan_lock = asyncio.Lock()

class ImportBody(BaseModel):
    services: list[dict]

async def perform_scan(imported=None):
    if scan_lock.locked(): raise HTTPException(409, "Er loopt al een scan")
    async with scan_lock:
        scan_id = store.start_scan()
        try:
            services = imported if imported is not None else await scanner.scan()
            store.apply_scan(scan_id, services, settings.removal_grace_scans)
            return {"scan_id": scan_id, "services": len(services), "status": "success"}
        except Exception as exc:
            store.fail_scan(scan_id, str(exc))
            raise

async def scheduler():
    if settings.scan_on_start:
        with contextlib.suppress(Exception): await perform_scan()
    while True:
        await asyncio.sleep(max(1, settings.scan_interval_minutes) * 60)
        with contextlib.suppress(Exception): await perform_scan()

@app.on_event("startup")
async def startup():
    if settings.enable_scheduler: app.state.scheduler = asyncio.create_task(scheduler())

@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "scheduler", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError): await task

@app.get("/")
def home(): return FileResponse(Path(__file__).parent / "static" / "index.html")

@app.get("/api/dashboard")
def dashboard(): return store.dashboard()

@app.get("/api/config")
def config():
    return {"adapter": settings.adapter, "frontend": settings.frontend,
            "tuning_file": settings.tuning_file, "interval_minutes": settings.scan_interval_minutes,
            "scheduler": settings.enable_scheduler, "scan_running": scan_lock.locked()}

@app.post("/api/scans")
async def scan_now():
    try: return await perform_scan()
    except HTTPException: raise
    except Exception as exc: raise HTTPException(500, str(exc))

@app.post("/api/scans/import")
async def import_scan(body: ImportBody):
    try: return await perform_scan(body.services)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400, str(exc))

@app.get("/health")
def health(): return {"status": "ok"}
