import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TRACKED = ("name", "provider", "channel_number", "frequency", "modulation", "symbol_rate",
           "encrypted", "teletext", "subtitles", "video", "audio")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def init(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS scan_runs (
              id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
              status TEXT NOT NULL, service_count INTEGER DEFAULT 0, message TEXT
            );
            CREATE TABLE IF NOT EXISTS services (
              service_key TEXT PRIMARY KEY, service_id INTEGER, original_network_id INTEGER,
              transport_stream_id INTEGER, name TEXT NOT NULL, provider TEXT,
              channel_number INTEGER, frequency INTEGER, modulation TEXT, symbol_rate INTEGER,
              encrypted INTEGER NOT NULL DEFAULT 0, teletext TEXT NOT NULL DEFAULT '[]',
              subtitles TEXT NOT NULL DEFAULT '[]', video TEXT NOT NULL DEFAULT '[]',
              audio TEXT NOT NULL DEFAULT '[]', first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
              last_scan_id INTEGER NOT NULL, missing_scans INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS service_snapshots (
              id INTEGER PRIMARY KEY, scan_id INTEGER NOT NULL, service_key TEXT NOT NULL,
              payload TEXT NOT NULL, observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS changes (
              id INTEGER PRIMARY KEY, scan_id INTEGER NOT NULL, service_key TEXT NOT NULL,
              service_name TEXT NOT NULL, kind TEXT NOT NULL, field TEXT,
              old_value TEXT, new_value TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_changes_created ON changes(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_snapshots_service ON service_snapshots(service_key, id DESC);
            """)

    def start_scan(self) -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO scan_runs(started_at,status) VALUES(?, 'running')", (now(),))
            return int(cur.lastrowid)

    def fail_scan(self, scan_id: int, message: str):
        with self.connect() as con:
            con.execute("UPDATE scan_runs SET finished_at=?,status='failed',message=? WHERE id=?",
                        (now(), message[:2000], scan_id))

    def apply_scan(self, scan_id: int, services: Iterable[dict[str, Any]], grace: int = 2):
        observed = now()
        normalized = [normalize(s) for s in services]
        keys = {s["service_key"] for s in normalized}
        with self.connect() as con:
            current = {r["service_key"]: dict(r) for r in con.execute("SELECT * FROM services")}
            for service in normalized:
                key = service["service_key"]
                old = current.get(key)
                if old is None:
                    self._change(con, scan_id, service, "added", None, None, service["name"], observed)
                    con.execute("""INSERT INTO services(
                      service_key,service_id,original_network_id,transport_stream_id,name,provider,
                      channel_number,frequency,modulation,symbol_rate,encrypted,teletext,subtitles,
                      video,audio,first_seen,last_seen,last_scan_id,missing_scans,active)
                      VALUES(:service_key,:service_id,:original_network_id,:transport_stream_id,:name,:provider,
                      :channel_number,:frequency,:modulation,:symbol_rate,:encrypted,:teletext,:subtitles,
                      :video,:audio,:first_seen,:last_seen,:last_scan_id,0,1)""",
                      db_payload(service, observed, scan_id))
                else:
                    for field in TRACKED:
                        before = decode(old[field]) if field in {"teletext","subtitles","video","audio"} else old[field]
                        after = service[field]
                        if before != after:
                            self._change(con, scan_id, service, "changed", field, before, after, observed)
                    p = db_payload(service, old["first_seen"], scan_id)
                    con.execute("""UPDATE services SET service_id=:service_id,
                      original_network_id=:original_network_id,transport_stream_id=:transport_stream_id,
                      name=:name,provider=:provider,channel_number=:channel_number,frequency=:frequency,
                      modulation=:modulation,symbol_rate=:symbol_rate,encrypted=:encrypted,
                      teletext=:teletext,subtitles=:subtitles,video=:video,audio=:audio,last_seen=:last_seen,
                      last_scan_id=:last_scan_id,missing_scans=0,active=1 WHERE service_key=:service_key""", p)
                con.execute("INSERT INTO service_snapshots(scan_id,service_key,payload,observed_at) VALUES(?,?,?,?)",
                            (scan_id, key, json.dumps(service, ensure_ascii=False, sort_keys=True), observed))

            for key, old in current.items():
                if key in keys or not old["active"]:
                    continue
                missing = old["missing_scans"] + 1
                if missing >= grace:
                    service = row_service(old)
                    self._change(con, scan_id, service, "removed", None, old["name"], None, observed)
                    con.execute("UPDATE services SET missing_scans=?,active=0 WHERE service_key=?", (missing, key))
                else:
                    con.execute("UPDATE services SET missing_scans=? WHERE service_key=?", (missing, key))
            con.execute("UPDATE scan_runs SET finished_at=?,status='success',service_count=? WHERE id=?",
                        (observed, len(normalized), scan_id))

    @staticmethod
    def _change(con, scan_id, s, kind, field, old, new, created):
        enc = lambda x: None if x is None else json.dumps(x, ensure_ascii=False)
        con.execute("""INSERT INTO changes(scan_id,service_key,service_name,kind,field,old_value,new_value,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (scan_id, s["service_key"], s["name"], kind, field, enc(old), enc(new), created))

    def dashboard(self) -> dict:
        with self.connect() as con:
            services = [row_service(dict(r)) for r in con.execute(
                "SELECT * FROM services WHERE active=1 ORDER BY channel_number IS NULL, channel_number, name")]
            changes = [dict(r) for r in con.execute("SELECT * FROM changes ORDER BY id DESC LIMIT 250")]
            runs = [dict(r) for r in con.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 30")]
            for c in changes:
                c["old_value"] = decode(c["old_value"])
                c["new_value"] = decode(c["new_value"])
            return {"services": services, "changes": changes, "runs": runs}


def decode(value):
    if value is None: return None
    try: return json.loads(value)
    except (TypeError, json.JSONDecodeError): return value


def row_service(r):
    for k in ("teletext", "subtitles", "video", "audio"):
        r[k] = decode(r.get(k)) or []
    r["encrypted"] = bool(r.get("encrypted"))
    return r


def db_payload(s, first_seen, scan_id):
    p = dict(s)
    for k in ("teletext", "subtitles", "video", "audio"):
        p[k] = json.dumps(p[k], ensure_ascii=False, sort_keys=True)
    p.update(first_seen=first_seen, last_seen=now(), last_scan_id=scan_id)
    p["encrypted"] = int(p["encrypted"])
    return p


def normalize(s):
    def integer(v):
        try: return int(str(v), 0)
        except (ValueError, TypeError): return None
    sid = integer(s.get("service_id"))
    onid = integer(s.get("original_network_id"))
    tsid = integer(s.get("transport_stream_id"))
    frequency = integer(s.get("frequency"))
    key = s.get("service_key") or (f"{onid}:{tsid}:{sid}" if None not in (onid,tsid,sid) else f"{frequency}:{sid}")
    return {
      "service_key": str(key), "service_id": sid, "original_network_id": onid,
      "transport_stream_id": tsid, "name": str(s.get("name") or f"Service {sid}"),
      "provider": s.get("provider"), "channel_number": integer(s.get("channel_number")),
      "frequency": frequency, "modulation": s.get("modulation"),
      "symbol_rate": integer(s.get("symbol_rate")), "encrypted": bool(s.get("encrypted", False)),
      "teletext": s.get("teletext") or [], "subtitles": s.get("subtitles") or [],
      "video": s.get("video") or [], "audio": s.get("audio") or []
    }
