from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatgpt_invoice_agent.config import load_config


class ConfigTests(unittest.TestCase):
    def test_berlin_timezone_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_dir.mkdir()
            path = config_dir / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "sender": "sender@example.com",
                        "recipient": "recipient@example.com",
                        "billing_day": 3,
                        "retry_offsets_days": [1, 2, 3],
                        "run_time": "08:00",
                        "timezone": "Europe/Berlin",
                        "filename_name": "Niels Welsch",
                        "archive_dir": "runtime/archive",
                        "state_file": "runtime/state.json",
                        "downloads_dir": "runtime/downloads",
                        "oauth_blob": "runtime/oauth.bin",
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.tzinfo.key, "Europe/Berlin")
            self.assertEqual(config.archive_dir, root / "runtime" / "archive")
            self.assertEqual(config.filename_name, "Niels Welsch")

    def test_portable_home_defaults_for_macos(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            config_dir = root / "config"
            config_dir.mkdir()
            path = config_dir / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "sender": "sender@example.com",
                        "recipient": "recipient@example.com",
                        "billing_day": 3,
                        "retry_offsets_days": [1, 2, 3],
                        "run_time": "08:00",
                        "timezone": "Europe/Berlin",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch("chatgpt_invoice_agent.config.Path.home", return_value=home),
                patch("chatgpt_invoice_agent.config.sys.platform", "darwin"),
            ):
                config = load_config(path)
            self.assertEqual(config.downloads_dir, (home / "Downloads").resolve())
            self.assertEqual(
                config.oauth_blob,
                (home / "Library" / "Application Support" / "ChatGPTInvoiceForwarder" / "oauth.bin").resolve(),
            )
            self.assertEqual(config.filename_name, "sender")


if __name__ == "__main__":
    unittest.main()
