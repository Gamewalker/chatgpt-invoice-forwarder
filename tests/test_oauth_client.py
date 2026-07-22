from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chatgpt_invoice_agent.errors import AuthenticationRequiredError
from chatgpt_invoice_agent.gmail_api import _load_client


class OAuthClientTests(unittest.TestCase):
    def test_desktop_client_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "client.json"
            path.write_text(
                json.dumps(
                    {
                        "installed": {
                            "client_id": "id",
                            "client_secret": "secret",
                            "auth_uri": "https://accounts.example/authorize",
                            "token_uri": "https://accounts.example/token",
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = _load_client(path)
            self.assertEqual(client["client_id"], "id")

    def test_web_client_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "client.json"
            path.write_text(json.dumps({"web": {"client_id": "id"}}), encoding="utf-8")
            with self.assertRaises(AuthenticationRequiredError):
                _load_client(path)


if __name__ == "__main__":
    unittest.main()

