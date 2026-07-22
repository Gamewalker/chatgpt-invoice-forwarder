from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import load_config
from .credential_store import credential_store_for
from .dates import is_scheduled_calendar_day
from .errors import (
    AuthenticationRequiredError,
    ConfigurationError,
    InvoiceAgentError,
    PermanentSendError,
    TemporarySendError,
    ValidationError,
)
from .gmail_api import REQUIRED_GMAIL_SCOPES, authorize, credentials_have_required_scopes
from .state import StateStore, public_status
from .workflow import find_download, ingest_invoice, send_invoice


def _json(value: Any, stream: Any = sys.stdout) -> None:
    json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    stream.write("\n")


def _datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Zeitpunkt muss ISO-8601 entsprechen.") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Zeitpunkt muss eine Zeitzone enthalten.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chatgpt-invoice-agent")
    parser.add_argument("--config", type=Path, help="Pfad zur agent.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth", help="Gmail OAuth einmalig einrichten")
    auth.add_argument("--client-secret", type=Path, required=True, help="Google Desktop-OAuth-JSON")
    auth.add_argument("--timeout", type=int, default=300)

    status = subparsers.add_parser("status", help="Status ohne Secrets anzeigen")
    status.add_argument("--invoice-id")

    guard = subparsers.add_parser("guard", help="Prüfen, ob heute ein geplanter Kalendertag ist")
    guard.add_argument("--today", type=date.fromisoformat)

    ingest = subparsers.add_parser("ingest", help="Download validieren und archivieren")
    ingest.add_argument("--pdf", type=Path)
    ingest.add_argument("--download-started-at", type=_datetime)
    ingest.add_argument("--invoice-date", type=date.fromisoformat, required=True)
    ingest.add_argument("--billing-name", required=True)
    ingest.add_argument("--invoice-number")
    ingest.add_argument("--source-url", required=True)

    send = subparsers.add_parser("send", help="Registrierte Rechnung idempotent senden")
    send.add_argument("--invoice-id", required=True)
    send.add_argument("--force", action="store_true", help="Nur für den einmaligen Abnahmelauf")
    send.add_argument("--today", type=date.fromisoformat, help=argparse.SUPPRESS)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    credential_store = credential_store_for(config)
    if args.command == "auth":
        return authorize(
            args.client_secret.resolve(), credential_store, config.sender, args.timeout
        )
    if args.command == "status":
        data = public_status(StateStore(config.state_file).load())
        oauth_configured = False
        if credential_store.exists(config.sender):
            try:
                oauth_configured = credentials_have_required_scopes(
                    credential_store.load(config.sender)
                )
            except AuthenticationRequiredError:
                oauth_configured = False
        credential_status = {
            "credential_backend": credential_store.backend_name,
            "oauth_configured": oauth_configured,
            "required_scopes": list(REQUIRED_GMAIL_SCOPES),
            "sender": config.sender,
            "recipient": config.recipient,
        }
        if args.invoice_id:
            return {
                "invoice": data["invoices"].get(args.invoice_id),
                "invoice_id": args.invoice_id,
                **credential_status,
            }
        return {**data, **credential_status}
    if args.command == "guard":
        today = args.today or datetime.now(config.tzinfo).date()
        return {
            "today": today,
            "scheduled": is_scheduled_calendar_day(
                today, config.billing_day, config.retry_offsets_days
            ),
        }
    if args.command == "ingest":
        pdf_path = args.pdf.resolve() if args.pdf else None
        if pdf_path is None:
            if args.download_started_at is None:
                raise ValidationError("Ohne --pdf ist --download-started-at erforderlich.")
            pdf_path = find_download(config.downloads_dir, args.download_started_at)
        record = ingest_invoice(
            config,
            pdf_path,
            args.invoice_date,
            args.billing_name,
            args.invoice_number,
            args.source_url,
        )
        return {"invoice": record, "invoice_id": record["invoice_id"]}
    if args.command == "send":
        return {"invoice": send_invoice(config, args.invoice_id, args.force, args.today)}
    raise AssertionError(f"Unbekannter Befehl: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _json(run(args))
        return 0
    except TemporarySendError as exc:
        _json({"error": str(exc), "type": type(exc).__name__, "temporary": True}, sys.stderr)
        return 75
    except (AuthenticationRequiredError, PermanentSendError) as exc:
        _json({"error": str(exc), "type": type(exc).__name__, "temporary": False}, sys.stderr)
        return 4
    except (ConfigurationError, ValidationError, InvoiceAgentError, ValueError, OSError) as exc:
        _json({"error": str(exc), "type": type(exc).__name__, "temporary": False}, sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
