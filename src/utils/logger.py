import contextlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any

_COMMIT_HASH: str | None = None
_VERSION: str | None = None


def _commit_hash() -> str | None:
    global _COMMIT_HASH
    if _COMMIT_HASH is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                _COMMIT_HASH = result.stdout.strip()
        except Exception:
            _COMMIT_HASH = None
    return _COMMIT_HASH


def _version() -> str | None:
    global _VERSION
    if _VERSION is None:
        with contextlib.suppress(PackageNotFoundError):
            _VERSION = pkg_version("openats-py")
        if _VERSION is None:
            try:
                import tomllib

                with open("pyproject.toml", "rb") as f:
                    data = tomllib.load(f)
                _VERSION = data.get("project", {}).get("version")
            except Exception:
                pass
    return _VERSION


_RESET = "\033[0m"
_GREY = "\033[90m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"


def _colorize_json(json_str: str, is_error: bool) -> str:
    lines = json_str.splitlines()
    out: list[str] = []
    value_color = _RED if is_error else _GREEN
    for line in lines:
        if '": ' in line:
            idx = line.index('": ') + 3
            key_part = line[:idx]
            value_part = line[idx:]
            out.append(f"{_CYAN}{key_part}{_RESET}{value_color}{value_part}{_RESET}")
        else:
            out.append(f"{_GREY}{line}{_RESET}")
    return "\n".join(out)


class EventLogger:
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self._run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def info(self, **payload: Any) -> None:
        self._emit("INFO", **payload)

    def error(self, **payload: Any) -> None:
        self._emit("ERROR", **payload)

    def _emit(self, severity: str, **payload: Any) -> None:
        event: dict[str, Any] = {
            "severity": severity,
            "timestamp": datetime.now(UTC).isoformat(),
            "service": self.service_name,
        }
        commit_hash = _commit_hash()
        if commit_hash:
            event["commit_hash"] = commit_hash
        version = _version()
        if version:
            event["version"] = version
        event.update(payload)

        json_str = json.dumps(event, indent=4)
        colorized = _colorize_json(json_str, severity == "ERROR")
        sys.stdout.write(colorized + "\n")
        sys.stdout.flush()

        if severity == "ERROR":
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/error{self._run_ts}", "a") as f:
                f.write(json_str + "\n")


logger = EventLogger(service_name="openats_collector_pipeline")
