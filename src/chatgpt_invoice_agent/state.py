from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "invoices": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != 1 or not isinstance(data.get("invoices"), dict):
            raise ValueError(f"Ungültiger Statusspeicher: {self.path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)

    def get(self, invoice_id: str) -> dict[str, Any] | None:
        record = self.load()["invoices"].get(invoice_id)
        return deepcopy(record) if record else None

    def find_by_hash(self, sha256: str) -> tuple[str, dict[str, Any]] | None:
        for invoice_id, record in self.load()["invoices"].items():
            if record.get("sha256") == sha256:
                return invoice_id, deepcopy(record)
        return None

    def upsert_ingested(self, invoice_id: str, record: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        existing = data["invoices"].get(invoice_id, {})
        if existing.get("status") == "sent":
            incoming_hash = record.get("sha256")
            if incoming_hash and existing.get("sha256") != incoming_hash:
                raise ValueError(f"Gesendete Rechnungs-ID {invoice_id} wurde mit anderem PDF-Inhalt angeboten.")
            return deepcopy(existing)
        attempts = existing.get("attempts", [])
        merged = {
            **existing,
            **record,
            "invoice_id": invoice_id,
            "status": "ready",
            "attempts": attempts,
            "updated_at": utc_now_iso(),
            "created_at": existing.get("created_at", utc_now_iso()),
        }
        data["invoices"][invoice_id] = merged
        self.save(data)
        return deepcopy(merged)

    def record_attempt(self, invoice_id: str, outcome: str, detail: str) -> dict[str, Any]:
        data = self.load()
        record = data["invoices"][invoice_id]
        record.setdefault("attempts", []).append(
            {"at": utc_now_iso(), "outcome": outcome, "detail": detail[:500]}
        )
        record["updated_at"] = utc_now_iso()
        if outcome == "failed":
            record["status"] = "retry_pending"
        self.save(data)
        return deepcopy(record)

    def mark_sent(
        self, invoice_id: str, gmail_message_id: str, dedupe_source: str | None = None
    ) -> dict[str, Any]:
        data = self.load()
        record = data["invoices"][invoice_id]
        record["status"] = "sent"
        record["gmail_message_id"] = gmail_message_id
        if dedupe_source:
            record["dedupe_source"] = dedupe_source
        record["sent_at"] = utc_now_iso()
        record["updated_at"] = record["sent_at"]
        self.save(data)
        return deepcopy(record)


def public_status(data: dict[str, Any]) -> dict[str, Any]:
    invoices: dict[str, Any] = {}
    for invoice_id, record in data.get("invoices", {}).items():
        invoices[invoice_id] = {
            key: value
            for key, value in record.items()
            if key not in {"source_url_hash"}
        }
    return {"version": data.get("version", 1), "invoices": invoices}
