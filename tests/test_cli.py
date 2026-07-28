from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from chatgpt_invoice_agent.cli import run
from chatgpt_invoice_agent.config import load_config
from chatgpt_invoice_agent.state import StateStore


class GuardTests(unittest.TestCase):
    def test_guard_uses_successful_send_as_monthly_switch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_dir.mkdir()
            config_path = config_dir / "agent.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sender": "sender@example.com",
                        "recipient": "recipient@example.com",
                        "billing_day": 3,
                        "retry_offsets_days": [1, 2, 3],
                        "run_time": "08:00",
                        "timezone": "Europe/Berlin",
                        "state_file": "runtime/state.json",
                        "oauth_blob": "runtime/oauth.bin",
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                command="guard",
                config=config_path,
                today=date(2026, 8, 20),
            )

            pending = run(args)
            self.assertTrue(pending["run_required"])
            self.assertEqual(pending["reason"], "not_completed")

            config = load_config(config_path)
            store = StateStore(config.state_file)
            store.upsert_ingested(
                "INV-8",
                {
                    "invoice_date": "2026-08-03",
                    "billing_name": "Example GmbH",
                    "file_path": "invoice.pdf",
                    "sha256": "abc",
                },
            )
            store.mark_sent("INV-8", "gmail-8")

            completed = run(args)
            self.assertFalse(completed["run_required"])
            self.assertTrue(completed["completed"])
            self.assertEqual(completed["completed_invoice_id"], "INV-8")
            self.assertEqual(completed["reason"], "already_completed")

    def test_guard_waits_until_first_eligible_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_dir.mkdir()
            config_path = config_dir / "agent.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sender": "sender@example.com",
                        "recipient": "recipient@example.com",
                        "billing_day": 3,
                        "retry_offsets_days": [1, 2, 3],
                        "run_time": "08:00",
                        "timezone": "Europe/Berlin",
                        "state_file": "runtime/state.json",
                        "oauth_blob": "runtime/oauth.bin",
                    }
                ),
                encoding="utf-8",
            )
            result = run(
                argparse.Namespace(
                    command="guard",
                    config=config_path,
                    today=date(2026, 8, 3),
                )
            )

            self.assertFalse(result["run_required"])
            self.assertEqual(result["eligible_from"], date(2026, 8, 4))
            self.assertEqual(result["reason"], "before_eligible_date")


if __name__ == "__main__":
    unittest.main()
