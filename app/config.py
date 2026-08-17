from dataclasses import dataclass
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database: str = os.getenv("DATABASE_PATH", "data/ziggo-monitor.db")
    adapter: int = int(os.getenv("DVB_ADAPTER", "0"))
    frontend: int = int(os.getenv("DVB_FRONTEND", "0"))
    tuning_file: str = os.getenv("DVB_TUNING_FILE", "/usr/share/dvb/dvb-c/nl-Ziggo")
    channels_file: str = os.getenv("DVB_CHANNELS_FILE", "data/channels.conf")
    scan_command: str = os.getenv("DVB_SCAN_COMMAND", "")
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "360"))
    scan_on_start: bool = _bool("SCAN_ON_START", False)
    enable_scheduler: bool = _bool("ENABLE_SCHEDULER", True)
    removal_grace_scans: int = int(os.getenv("REMOVAL_GRACE_SCANS", "2"))


settings = Settings()
