from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chatgpt_invoice_agent.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_ingest_retry_send_and_idempotent_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            record = store.upsert_ingested(
                "INV-1",
                {
                    "invoice_date": "2026-07-03",
                    "billing_name": "Example GmbH",
                    "file_path": "invoice.pdf",
                    "sha256": "abc",
                },
            )
            self.assertEqual(record["status"], "ready")
            store.record_attempt("INV-1", "failed", "network")
            self.assertEqual(store.get("INV-1")["status"], "retry_pending")
            store.mark_sent("INV-1", "gmail-123")
            sent = store.get("INV-1")
            self.assertEqual(sent["status"], "sent")
            self.assertEqual(sent["gmail_message_id"], "gmail-123")
            unchanged = store.upsert_ingested("INV-1", {"sha256": "abc"})
            self.assertEqual(unchanged["sha256"], "abc")
            with self.assertRaises(ValueError):
                store.upsert_ingested("INV-1", {"sha256": "different"})


if __name__ == "__main__":
    unittest.main()
