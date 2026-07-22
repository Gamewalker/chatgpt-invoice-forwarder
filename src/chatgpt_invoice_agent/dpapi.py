from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .errors import AuthenticationRequiredError


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_DESCRIPTION = "ChatGPTInvoiceForwarder"
_ENTROPY = b"chatgpt-invoice-forwarder:v1"


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _require_windows() -> None:
    if os.name != "nt":
        raise AuthenticationRequiredError("DPAPI-Speicherung wird nur unter Windows unterstützt.")


def protect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, input_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    output_blob = _DataBlob()
    result = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        _DESCRIPTION,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    del input_buffer, entropy_buffer
    if not result:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def unprotect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, input_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(_ENTROPY)
    output_blob = _DataBlob()
    result = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    del input_buffer, entropy_buffer
    if not result:
        raise AuthenticationRequiredError("OAuth-Daten können für diesen Windows-Benutzer nicht entschlüsselt werden.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    protected = protect(encoded)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(protected)
    os.replace(temp, path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AuthenticationRequiredError(
            f"Gmail OAuth ist noch nicht eingerichtet. Führe zuerst 'auth' aus. Erwartet: {path}"
        )
    try:
        decoded = unprotect(path.read_bytes())
        payload = json.loads(decoded.decode("utf-8"))
    except AuthenticationRequiredError:
        raise
    except Exception as exc:
        raise AuthenticationRequiredError(f"OAuth-Daten sind ungültig: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuthenticationRequiredError("OAuth-Daten haben ein ungültiges Format.")
    return payload

