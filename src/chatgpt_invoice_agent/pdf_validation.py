from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errors import ValidationError


_MONTHS_DE = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
_MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class PdfValidationResult:
    sha256: str
    page_count: int
    text: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _normalized_identifier(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _date_variants(value: date) -> tuple[str, ...]:
    month_de = _MONTHS_DE[value.month - 1]
    month_en = _MONTHS_EN[value.month - 1]
    return (
        value.isoformat(),
        value.strftime("%d.%m.%Y"),
        f"{value.day}.{value.month:02d}.{value.year}",
        f"{value.day}. {month_de} {value.year}",
        f"{value.day} {month_de} {value.year}",
        f"{month_en} {value.day}, {value.year}",
    )


def validate_invoice_pdf(path: Path, invoice_date: date, invoice_number: str | None = None) -> PdfValidationResult:
    try:
        signature = path.read_bytes()[:5]
    except OSError as exc:
        raise ValidationError(f"PDF kann nicht gelesen werden: {path}: {exc}") from exc
    if signature != b"%PDF-":
        raise ValidationError("Datei besitzt keine gültige PDF-Signatur.")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValidationError("pypdf fehlt. Installiere das Projekt zuerst in der lokalen Umgebung.") from exc

    try:
        reader = PdfReader(str(path))
        extracted = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
        metadata = " ".join(str(value) for value in (reader.metadata or {}).values() if value)
    except Exception as exc:
        raise ValidationError(f"PDF-Inhalt kann nicht gelesen werden: {exc}") from exc

    searchable = _normalized(f"{metadata}\n{extracted}")
    if "openai" not in searchable:
        raise ValidationError("OpenAI wurde im Rechnungs-PDF nicht als Aussteller gefunden.")

    normalized_variants = tuple(_normalized(value) for value in _date_variants(invoice_date))
    if not any(variant in searchable for variant in normalized_variants):
        raise ValidationError(f"Rechnungsdatum {invoice_date.isoformat()} wurde im PDF nicht gefunden.")

    if invoice_number and _normalized_identifier(invoice_number) not in _normalized_identifier(searchable):
        raise ValidationError(f"Rechnungsnummer {invoice_number} wurde im PDF nicht gefunden.")

    return PdfValidationResult(
        sha256=sha256_file(path),
        page_count=len(reader.pages),
        text=extracted,
    )
