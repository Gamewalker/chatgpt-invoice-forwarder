from __future__ import annotations

import tempfile
import unittest
import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import patch

from chatgpt_invoice_agent.config import AgentConfig
from chatgpt_invoice_agent.errors import TemporarySendError
from chatgpt_invoice_agent.state import StateStore
from chatgpt_invoice_agent.workflow import ingest_invoice, send_invoice


class WorkflowTests(unittest.TestCase):
    def test_ingest_uses_configured_person_and_month_for_filename(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AgentConfig(
                sender="sender@example.com",
                recipient="recipient@example.com",
                billing_day=3,
                retry_offsets_days=(1, 2, 3),
                run_time="08:00",
                timezone="Europe/Berlin",
                archive_dir=root / "archive",
                state_file=root / "state.json",
                downloads_dir=root / "downloads",
                oauth_blob=root / "oauth.bin",
                source_path=root / "agent.json",
                filename_name="Niels Welsch",
            )
            source = root / "download.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.add_metadata({"/Title": "OpenAI Rechnung 3. Juli 2026 INV-1"})
            with source.open("wb") as handle:
                writer.write(handle)

            record = ingest_invoice(
                config,
                source,
                date(2026, 7, 3),
                "RAIVA Technologies GmbH",
                "INV-1",
                "https://invoice.example/INV-1",
            )
            archived = Path(record["file_path"])
            self.assertEqual(archived.name, "Rechnung_CHATGPT_Niels_Welsch_072026.pdf")
            self.assertTrue(archived.exists())

    def test_sent_invoice_is_noop_without_gmail_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AgentConfig(
                sender="sender@example.com",
                recipient="recipient@example.com",
                billing_day=3,
                retry_offsets_days=(1, 2, 3),
                run_time="08:00",
                timezone="Europe/Berlin",
                archive_dir=root / "archive",
                state_file=root / "state.json",
                downloads_dir=root / "downloads",
                oauth_blob=root / "oauth.bin",
                source_path=root / "agent.json",
            )
            store = StateStore(config.state_file)
            store.upsert_ingested(
                "INV-1",
                {
                    "invoice_date": "2026-07-03",
                    "billing_name": "Example GmbH",
                    "invoice_number": "INV-1",
                    "file_path": str(root / "missing-is-ok-after-sent.pdf"),
                    "sha256": "abc",
                },
            )
            store.mark_sent("INV-1", "gmail-123")
            with patch("chatgpt_invoice_agent.workflow.send_message") as gmail_send:
                result = send_invoice(config, "INV-1", force=True, today=date(2026, 7, 22))
            self.assertTrue(result["noop"])
            self.assertEqual(result["dedupe_source"], "local_state")
            gmail_send.assert_not_called()

    def test_gmail_sent_match_is_persisted_without_sending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AgentConfig(
                sender="sender@example.com",
                recipient="recipient@example.com",
                billing_day=3,
                retry_offsets_days=(1, 2, 3),
                run_time="08:00",
                timezone="Europe/Berlin",
                archive_dir=root / "archive",
                state_file=root / "state.json",
                downloads_dir=root / "downloads",
                oauth_blob=root / "oauth.bin",
                source_path=root / "agent.json",
            )
            attachment = root / "invoice.pdf"
            attachment.write_bytes(b"%PDF-test")
            digest = hashlib.sha256(attachment.read_bytes()).hexdigest()
            store = StateStore(config.state_file)
            store.upsert_ingested(
                "INV-1",
                {
                    "invoice_date": "2026-07-03",
                    "billing_name": "Example GmbH",
                    "invoice_number": "INV-1",
                    "file_path": str(attachment),
                    "sha256": digest,
                },
            )
            with (
                patch("chatgpt_invoice_agent.workflow.credential_store_for", return_value=object()),
                patch("chatgpt_invoice_agent.workflow.find_sent_message", return_value="gmail-existing"),
                patch("chatgpt_invoice_agent.workflow.send_message") as gmail_send,
            ):
                result = send_invoice(config, "INV-1", force=True, today=date(2026, 7, 22))
            self.assertTrue(result["noop"])
            self.assertEqual(result["dedupe_source"], "gmail_sent")
            self.assertEqual(store.get("INV-1")["gmail_message_id"], "gmail-existing")
            gmail_send.assert_not_called()

    def test_gmail_lookup_failure_prevents_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AgentConfig(
                sender="sender@example.com",
                recipient="recipient@example.com",
                billing_day=3,
                retry_offsets_days=(1, 2, 3),
                run_time="08:00",
                timezone="Europe/Berlin",
                archive_dir=root / "archive",
                state_file=root / "state.json",
                downloads_dir=root / "downloads",
                oauth_blob=root / "oauth.bin",
                source_path=root / "agent.json",
            )
            attachment = root / "invoice.pdf"
            attachment.write_bytes(b"%PDF-test")
            digest = hashlib.sha256(attachment.read_bytes()).hexdigest()
            store = StateStore(config.state_file)
            store.upsert_ingested(
                "INV-1",
                {
                    "invoice_date": "2026-07-03",
                    "billing_name": "Example GmbH",
                    "invoice_number": "INV-1",
                    "file_path": str(attachment),
                    "sha256": digest,
                },
            )
            with (
                patch("chatgpt_invoice_agent.workflow.credential_store_for", return_value=object()),
                patch(
                    "chatgpt_invoice_agent.workflow.find_sent_message",
                    side_effect=TemporarySendError("lookup unavailable"),
                ),
                patch("chatgpt_invoice_agent.workflow.send_message") as gmail_send,
            ):
                with self.assertRaises(TemporarySendError):
                    send_invoice(config, "INV-1", force=True, today=date(2026, 7, 22))
            self.assertEqual(store.get("INV-1")["status"], "retry_pending")
            gmail_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
