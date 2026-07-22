from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from . import dpapi
from .config import AgentConfig
from .errors import AuthenticationRequiredError


MACOS_KEYCHAIN_SERVICE = "io.raiva.chatgpt-invoice-forwarder.oauth"


class CredentialStore(Protocol):
    backend_name: str

    def exists(self, sender: str) -> bool: ...

    def load(self, sender: str) -> dict[str, Any]: ...

    def save(self, sender: str, payload: dict[str, Any]) -> None: ...


class WindowsDpapiStore:
    backend_name = "windows-dpapi"

    def __init__(self, path: Path):
        self.path = path

    def exists(self, sender: str) -> bool:
        del sender
        return self.path.exists()

    def load(self, sender: str) -> dict[str, Any]:
        del sender
        return dpapi.load_json(self.path)

    def save(self, sender: str, payload: dict[str, Any]) -> None:
        del sender
        dpapi.save_json(self.path, payload)


class MacOSKeychainStore:
    backend_name = "macos-keychain"

    def __init__(self, service: str = MACOS_KEYCHAIN_SERVICE, keyring_module: Any | None = None):
        self.service = service
        self._keyring_module = keyring_module

    def _keyring(self) -> Any:
        if self._keyring_module is not None:
            return self._keyring_module
        try:
            self._keyring_module = importlib.import_module("keyring")
        except ImportError as exc:
            raise AuthenticationRequiredError(
                "macOS-Schlüsselbund-Unterstützung fehlt. Führe zuerst scripts/setup.sh aus."
            ) from exc
        return self._keyring_module

    @staticmethod
    def _account(sender: str) -> str:
        return sender.strip().casefold()

    def _get_password(self, sender: str) -> str | None:
        try:
            return self._keyring().get_password(self.service, self._account(sender))
        except Exception as exc:
            raise AuthenticationRequiredError(f"macOS-Schlüsselbund ist nicht verfügbar: {exc}") from exc

    def exists(self, sender: str) -> bool:
        return self._get_password(sender) is not None

    def load(self, sender: str) -> dict[str, Any]:
        encoded = self._get_password(sender)
        if encoded is None:
            raise AuthenticationRequiredError(
                "Gmail OAuth ist im macOS-Schlüsselbund noch nicht eingerichtet. Führe zuerst 'auth' aus."
            )
        try:
            payload = json.loads(encoded)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AuthenticationRequiredError("OAuth-Daten im macOS-Schlüsselbund sind ungültig.") from exc
        if not isinstance(payload, dict):
            raise AuthenticationRequiredError("OAuth-Daten im macOS-Schlüsselbund haben ein ungültiges Format.")
        return payload

    def save(self, sender: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            self._keyring().set_password(self.service, self._account(sender), encoded)
        except Exception as exc:
            raise AuthenticationRequiredError(
                f"OAuth-Daten konnten nicht im macOS-Schlüsselbund gespeichert werden: {exc}"
            ) from exc


def credential_store_for(
    config: AgentConfig,
    platform_name: str | None = None,
    keyring_module: Any | None = None,
) -> CredentialStore:
    selected = platform_name or sys.platform
    if selected == "win32":
        return WindowsDpapiStore(config.oauth_blob)
    if selected == "darwin":
        return MacOSKeychainStore(keyring_module=keyring_module)
    raise AuthenticationRequiredError(
        f"Nicht unterstütztes Betriebssystem für sichere OAuth-Speicherung: {selected}"
    )
