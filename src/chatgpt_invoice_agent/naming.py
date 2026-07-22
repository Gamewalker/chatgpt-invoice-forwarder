from __future__ import annotations

import re
import unicodedata
from datetime import date


_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SEPARATORS = re.compile(r"[\s_-]+")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_component(value: str, max_length: int = 96) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _INVALID.sub("-", normalized)
    normalized = _SEPARATORS.sub("-", normalized).strip(" .-_")
    if not normalized:
        normalized = "Unbekannt"
    if normalized.upper() in _RESERVED:
        normalized = f"_{normalized}"
    return normalized[:max_length].rstrip(" .-_") or "Unbekannt"


def safe_person_component(value: str, max_length: int = 96) -> str:
    return safe_component(value, max_length).replace("-", "_")


def invoice_filename(filename_name: str, invoice_date: date) -> str:
    return (
        f"Rechnung_CHATGPT_{safe_person_component(filename_name)}_"
        f"{invoice_date.strftime('%m%Y')}.pdf"
    )


def message_subject(billing_name: str, invoice_date: date) -> str:
    return f"ChatGPT-Rechnung – {billing_name.strip()} – {invoice_date.strftime('%d.%m.%Y')}"
