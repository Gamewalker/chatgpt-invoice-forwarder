from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatgpt_invoice_agent.config import AgentConfig
from chatgpt_invoice_agent.credential_store import (
    MACOS_KEYCHAIN_SERVICE,
    MacOSKeychainStore,
    WindowsDpapiStore,
    credential_store_for,
)
from chatgpt_invoice_agent.errors import AuthenticationRequiredError


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def set_password(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value


def make_config(root: Path) -> AgentConfig:
    return AgentConfig(
        sender="Sender@Example.com",
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


class CredentialStoreTests(unittest.TestCase):
    def test_macos_keychain_roundtrip_uses_normalized_account(self) -> None:
        keyring = FakeKeyring()
        store = MacOSKeychainStore(keyring_module=keyring)
        payload = {"version": 2, "refresh_token": "secret"}
        store.save("Sender@Example.com", payload)
        self.assertEqual(store.load("sender@example.com"), payload)
        encoded = keyring.values[(MACOS_KEYCHAIN_SERVICE, "sender@example.com")]
        self.assertEqual(json.loads(encoded), payload)

    def test_macos_keychain_failure_never_falls_back_to_plaintext(self) -> None:
        class BrokenKeyring:
            def get_password(self, service: str, account: str) -> str | None:
                raise RuntimeError("locked")

        with self.assertRaises(AuthenticationRequiredError):
            MacOSKeychainStore(keyring_module=BrokenKeyring()).exists("sender@example.com")

    def test_platform_backend_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            self.assertIsInstance(credential_store_for(config, "win32"), WindowsDpapiStore)
            self.assertIsInstance(
                credential_store_for(config, "darwin", FakeKeyring()), MacOSKeychainStore
            )
            with self.assertRaises(AuthenticationRequiredError):
                credential_store_for(config, "linux")

    def test_windows_store_keeps_dpapi_blob_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oauth.bin"
            path.write_bytes(b"encrypted")
            store = WindowsDpapiStore(path)
            with (
                patch("chatgpt_invoice_agent.credential_store.dpapi.load_json", return_value={"version": 1}) as load,
                patch("chatgpt_invoice_agent.credential_store.dpapi.save_json") as save,
            ):
                self.assertEqual(store.load("sender@example.com"), {"version": 1})
                store.save("sender@example.com", {"version": 2})
            load.assert_called_once_with(path)
            save.assert_called_once_with(path, {"version": 2})


if __name__ == "__main__":
    unittest.main()
