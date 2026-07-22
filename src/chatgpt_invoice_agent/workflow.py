from __future__ import annotations

import hashlib
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import AgentConfig
from .credential_store import credential_store_for
from .dates import is_send_day
from .errors import AmbiguousDownloadError, ValidationError
from .gmail_api import (
    build_message,
    deterministic_message_id,
    find_sent_message,
    send_message,
)
from .naming import invoice_filename, message_subject
from .pdf_validation import sha256_file, validate_invoice_pdf
from .state import StateStore


def source_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()


def invoice_id(invoice_date: date, invoice_number: str | None, source_url: str) -> str:
    if invoice_number:
        return invoice_number.strip()
    return f"{invoice_date.isoformat()}-{source_hash(source_url)[:16]}"


def find_download(downloads_dir: Path, started_at: datetime) -> Path:
    if not downloads_dir.exists():
        raise AmbiguousDownloadError(f"Download-Ordner fehlt: {downloads_dir}")
    threshold = started_at.astimezone(timezone.utc).timestamp() - 2
    candidates = [
        path
        for path in downloads_dir.glob("*.pdf")
        if path.is_file() and path.stat().st_mtime >= threshold and not path.name.endswith(".crdownload")
    ]
    if len(candidates) != 1:
        names = ", ".join(path.name for path in sorted(candidates)) or "keine"
        raise AmbiguousDownloadError(
            f"Erwartet wurde genau eine neue PDF seit {started_at.isoformat()}, gefunden: {names}"
        )
    return candidates[0]


def ingest_invoice(
    config: AgentConfig,
    pdf_path: Path,
    invoice_date_value: date,
    billing_name: str,
    invoice_number: str | None,
    source_url: str,
) -> dict[str, Any]:
    validation = validate_invoice_pdf(pdf_path, invoice_date_value, invoice_number)
    store = StateStore(config.state_file)
    duplicate = store.find_by_hash(validation.sha256)
    target_id = invoice_id(invoice_date_value, invoice_number, source_url)
    if duplicate and duplicate[0] != target_id:
        raise ValidationError(f"PDF wurde bereits unter Rechnungs-ID {duplicate[0]} registriert.")

    year_dir = config.archive_dir / str(invoice_date_value.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    archived = year_dir / invoice_filename(
        config.filename_name or billing_name, invoice_date_value
    )
    if archived.exists() and sha256_file(archived) != validation.sha256:
        raise ValidationError(f"Archivziel existiert bereits mit anderem Inhalt: {archived}")
    if not archived.exists():
        temp = archived.with_suffix(".pdf.tmp")
        shutil.copy2(pdf_path, temp)
        os.replace(temp, archived)

    record = store.upsert_ingested(
        target_id,
        {
            "invoice_date": invoice_date_value.isoformat(),
            "invoice_number": invoice_number or "",
            "billing_name": billing_name.strip(),
            "source_url_hash": source_hash(source_url),
            "file_path": str(archived),
            "sha256": validation.sha256,
            "page_count": validation.page_count,
        },
    )
    return record


def send_invoice(config: AgentConfig, target_id: str, force: bool = False, today: date | None = None) -> dict[str, Any]:
    store = StateStore(config.state_file)
    record = store.get(target_id)
    if record is None:
        raise ValidationError(f"Unbekannte Rechnungs-ID: {target_id}")
    if record.get("status") == "sent":
        return {**record, "noop": True, "dedupe_source": "local_state"}

    invoice_date_value = date.fromisoformat(str(record["invoice_date"]))
    local_today = today or datetime.now(config.tzinfo).date()
    if not force and not is_send_day(local_today, invoice_date_value, config.retry_offsets_days):
        allowed = ", ".join(value.isoformat() for value in (
            invoice_date_value + timedelta(days=offset)
            for offset in config.retry_offsets_days
        ))
        raise ValidationError(f"Versand ist heute nicht vorgesehen. Erlaubte Tage: {allowed}")

    attachment = Path(str(record["file_path"]))
    if not attachment.exists() or sha256_file(attachment) != record.get("sha256"):
        raise ValidationError("Archivierte PDF fehlt oder stimmt nicht mit dem registrierten Hash überein.")

    subject = message_subject(str(record["billing_name"]), invoice_date_value)
    number_line = f"Rechnungsnummer: {record['invoice_number']}\n" if record.get("invoice_number") else ""
    body = (
        "Anbei die ChatGPT-Rechnung.\n\n"
        f"Abrechnungsname: {record['billing_name']}\n"
        f"Rechnungsdatum: {invoice_date_value.strftime('%d.%m.%Y')}\n"
        f"{number_line}"
    )
    message_id = deterministic_message_id(target_id, str(record["sha256"]), config.sender)
    credential_store = credential_store_for(config)
    try:
        existing_message_id = find_sent_message(
            credential_store,
            config.sender,
            config.recipient,
            subject,
            message_id,
        )
        if existing_message_id:
            store.record_attempt(
                target_id,
                "deduplicated",
                f"Bereits im Gmail-Gesendet-Ordner: {existing_message_id}",
            )
            sent = store.mark_sent(target_id, existing_message_id, "gmail_sent")
            return {**sent, "noop": True, "dedupe_source": "gmail_sent"}

        message = build_message(
            config.sender,
            config.recipient,
            subject,
            body,
            attachment,
            message_id=message_id,
        )
        gmail_message_id = send_message(credential_store, message, config.sender)
    except Exception as exc:
        store.record_attempt(target_id, "failed", f"{type(exc).__name__}: {exc}")
        raise
    store.record_attempt(target_id, "sent", f"Gmail message id: {gmail_message_id}")
    sent = store.mark_sent(target_id, gmail_message_id, "gmail_send")
    return {**sent, "noop": False, "dedupe_source": "gmail_send"}
