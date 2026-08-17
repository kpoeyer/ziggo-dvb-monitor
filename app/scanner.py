import asyncio
import configparser
import json
import os
import shlex
from pathlib import Path
from .config import Settings


class Scanner:
    def __init__(self, cfg: Settings): self.cfg = cfg

    async def scan(self) -> list[dict]:
        Path(self.cfg.channels_file).parent.mkdir(parents=True, exist_ok=True)
        if self.cfg.scan_command:
            command = self.cfg.scan_command.format(
                adapter=self.cfg.adapter, frontend=self.cfg.frontend,
                tuning_file=shlex.quote(self.cfg.tuning_file),
                channels_file=shlex.quote(self.cfg.channels_file))
        else:
            command = (f"dvbv5-scan -a {self.cfg.adapter} -f {self.cfg.frontend} "
                       f"-o {shlex.quote(self.cfg.channels_file)} {shlex.quote(self.cfg.tuning_file)}")
        proc = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.STDOUT)
        output, _ = await proc.communicate()
        if proc.returncode:
            raise RuntimeError(f"Scan-commando faalde ({proc.returncode}):\n{output.decode(errors='replace')}")
        # A custom command may print the complete normalized JSON directly.
        text = output.decode(errors="replace").strip()
        if text.startswith("["):
            return json.loads(text)
        return parse_dvbv5(self.cfg.channels_file)


def parse_dvbv5(path: str) -> list[dict]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str.upper
    with open(path, encoding="utf-8", errors="replace") as f:
        parser.read_file(f)
    result = []
    for name in parser.sections():
        d = parser[name]
        get = lambda *names: next((d[n] for n in names if n in d), None)
        def streams(*names):
            value = get(*names)
            if not value: return []
            return [{"pid": as_int(x.strip())} for x in value.replace(";", ",").split(",") if x.strip()]
        result.append({
          "name": name, "service_id": as_int(get("SERVICE_ID", "PROGRAM_NUMBER")),
          "original_network_id": as_int(get("NETWORK_ID", "ORIGINAL_NETWORK_ID")),
          "transport_stream_id": as_int(get("TRANSPORT_ID", "TRANSPORT_STREAM_ID")),
          "provider": get("PROVIDER"), "channel_number": as_int(get("VCHANNEL", "LCN", "CHANNEL_NUMBER")),
          "frequency": as_int(get("FREQUENCY")), "symbol_rate": as_int(get("SYMBOL_RATE")),
          "modulation": get("MODULATION"), "encrypted": str(get("SCRAMBLED", "ENCRYPTED") or "0").lower() in ("1","true","yes"),
          "teletext": streams("TELETEXT_PID", "TELETEXT"),
          "subtitles": streams("SUBTITLE_PID", "SUBTITLES"),
          "video": streams("VIDEO_PID"), "audio": streams("AUDIO_PID")
        })
    if not result: raise RuntimeError(f"Geen zenders gevonden in {path}")
    return result


def as_int(value):
    if value is None: return None
    try: return int(str(value).strip(), 0)
    except ValueError:
        try: return int(str(value).strip().split()[0])
        except (ValueError, IndexError): return None
