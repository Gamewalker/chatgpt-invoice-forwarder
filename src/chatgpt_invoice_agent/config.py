from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from .errors import ConfigurationError


def _expand_path(value: str, base: Path) -> Path:
    expanded_value = os.path.expandvars(value)
    if expanded_value == "~":
        expanded = Path.home()
    elif expanded_value.startswith(("~/", "~\\")):
        expanded = Path.home() / expanded_value[2:]
    else:
        expanded = Path(expanded_value)
    if not expanded.is_absolute():
        expanded = base / expanded
    return expanded.resolve()


def _default_oauth_blob() -> Path:
    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "ChatGPTInvoiceForwarder" / "oauth.bin"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ChatGPTInvoiceForwarder" / "oauth.bin"
    return Path.home() / ".local" / "share" / "ChatGPTInvoiceForwarder" / "oauth.bin"


@dataclass(frozen=True)
class AgentConfig:
    sender: str
    recipient: str
    billing_day: int
    retry_offsets_days: tuple[int, ...]
    run_time: str
    timezone: str
    archive_dir: Path
    state_file: Path
    downloads_dir: Path
    oauth_blob: Path
    source_path: Path
    filename_name: str = ""

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def default_config_path() -> Path:
    configured = os.getenv("CHATGPT_INVOICE_CONFIG")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "config" / "agent.json").resolve()


def load_config(path: Path | None = None) -> AgentConfig:
    source = (path or default_config_path()).resolve()
    if not source.exists():
        raise ConfigurationError(f"Konfiguration fehlt: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Konfiguration kann nicht gelesen werden: {exc}") from exc

    required = ("sender", "recipient", "billing_day", "retry_offsets_days", "run_time", "timezone")
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigurationError(f"Fehlende Konfigurationsfelder: {', '.join(missing)}")

    sender = str(data["sender"]).strip()
    recipient = str(data["recipient"]).strip()
    if "@" not in sender or "@" not in recipient:
        raise ConfigurationError("Absender und Empfänger müssen E-Mail-Adressen sein.")
    filename_name = str(
        data.get("filename_name") or sender.split("@", 1)[0].replace(".", " ")
    ).strip()
    if not filename_name:
        raise ConfigurationError("filename_name darf nicht leer sein.")

    billing_day = int(data["billing_day"])
    if not 1 <= billing_day <= 28:
        raise ConfigurationError("billing_day muss zwischen 1 und 28 liegen.")
    offsets = tuple(sorted({int(value) for value in data["retry_offsets_days"]}))
    if not offsets or offsets[0] < 1:
        raise ConfigurationError("retry_offsets_days muss positive Tagesabstände enthalten.")

    try:
        ZoneInfo(str(data["timezone"]))
    except Exception as exc:
        raise ConfigurationError(f"Ungültige Zeitzone: {data['timezone']}") from exc

    base = source.parent.parent
    return AgentConfig(
        sender=sender,
        recipient=recipient,
        billing_day=billing_day,
        retry_offsets_days=offsets,
        run_time=str(data["run_time"]),
        timezone=str(data["timezone"]),
        archive_dir=_expand_path(str(data.get("archive_dir", "runtime/archive")), base),
        state_file=_expand_path(str(data.get("state_file", "runtime/state.json")), base),
        downloads_dir=_expand_path(str(data.get("downloads_dir", "~/Downloads")), base),
        oauth_blob=(
            _expand_path(str(data["oauth_blob"]), base)
            if data.get("oauth_blob")
            else _default_oauth_blob().resolve()
        ),
        source_path=source,
        filename_name=filename_name,
    )
