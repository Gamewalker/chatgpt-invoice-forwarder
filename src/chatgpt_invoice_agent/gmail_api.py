from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from email.message import EmailMessage
from email.utils import getaddresses
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .credential_store import CredentialStore
from .errors import AuthenticationRequiredError, PermanentSendError, TemporarySendError


GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
REQUIRED_GMAIL_SCOPES = tuple(sorted((GMAIL_READONLY_SCOPE, GMAIL_SEND_SCOPE)))
GMAIL_SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_MESSAGES_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def _json_post(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _json_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _form_post(url: str, payload: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AuthenticationRequiredError(f"Google OAuth wurde abgelehnt ({exc.code}): {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise TemporarySendError(f"Google OAuth ist vorübergehend nicht erreichbar: {exc.reason}") from exc


def _load_client(client_secret_path: Path) -> dict[str, str]:
    try:
        payload = json.loads(client_secret_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthenticationRequiredError(f"OAuth-Client-Datei kann nicht gelesen werden: {exc}") from exc
    client = payload.get("installed")
    if not isinstance(client, dict):
        raise AuthenticationRequiredError("Erwartet wird ein Google OAuth-Client vom Typ Desktop-App.")
    required = ("client_id", "client_secret", "auth_uri", "token_uri")
    missing = [key for key in required if not client.get(key)]
    if missing:
        raise AuthenticationRequiredError(f"OAuth-Client enthält nicht: {', '.join(missing)}")
    return {key: str(client[key]) for key in required}


def authorize(
    client_secret_path: Path,
    credential_store: CredentialStore,
    sender: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    client = _load_client(client_secret_path)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["state"] = query.get("state", [""])[0]
            result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            ok = bool(result["code"]) and result["state"] == state
            body = (
                "Gmail-Autorisierung abgeschlossen. Dieses Fenster kann geschlossen werden."
                if ok
                else "Gmail-Autorisierung fehlgeschlagen. Bitte zum Agenten zurückkehren."
            )
            encoded = body.encode("utf-8")
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = 1
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    parameters = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(REQUIRED_GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "login_hint": sender,
        "include_granted_scopes": "false",
    }
    authorization_url = f"{client['auth_uri']}?{urllib.parse.urlencode(parameters)}"
    if not webbrowser.open(authorization_url, new=1):
        print(f"Öffne diese URL im Browser:\n{authorization_url}")
    print(f"Warte auf die Google-Freigabe für {sender} …", flush=True)

    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline and not result.get("code") and not result.get("error"):
            server.handle_request()
    finally:
        server.server_close()

    if result.get("error"):
        raise AuthenticationRequiredError(f"Google OAuth wurde abgebrochen: {result['error']}")
    if not result.get("code") or result.get("state") != state:
        raise AuthenticationRequiredError("Google OAuth wurde nicht rechtzeitig oder mit ungültigem Status abgeschlossen.")

    token = _form_post(
        client["token_uri"],
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": result["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if not token.get("refresh_token"):
        raise AuthenticationRequiredError("Google hat kein Refresh-Token zurückgegeben; Zugriff widerrufen und erneut autorisieren.")

    credentials = {
        "version": 2,
        "sender": sender,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "token_uri": client["token_uri"],
        "refresh_token": token["refresh_token"],
        "access_token": token.get("access_token", ""),
        "expires_at": time.time() + int(token.get("expires_in", 0)),
        "scopes": list(REQUIRED_GMAIL_SCOPES),
    }
    credential_store.save(sender, credentials)
    return {
        "sender": sender,
        "credential_backend": credential_store.backend_name,
        "scopes": list(REQUIRED_GMAIL_SCOPES),
    }


def credentials_have_required_scopes(credentials: dict[str, Any]) -> bool:
    scopes = credentials.get("scopes")
    if not isinstance(scopes, list):
        return False
    return credentials.get("version") == 2 and set(REQUIRED_GMAIL_SCOPES).issubset(
        {str(scope) for scope in scopes}
    )


def _refresh(
    credentials: dict[str, Any], credential_store: CredentialStore, sender: str
) -> str:
    token = _form_post(
        str(credentials["token_uri"]),
        {
            "client_id": str(credentials["client_id"]),
            "client_secret": str(credentials["client_secret"]),
            "refresh_token": str(credentials["refresh_token"]),
            "grant_type": "refresh_token",
        },
    )
    access_token = str(token.get("access_token", ""))
    if not access_token:
        raise AuthenticationRequiredError("Google hat kein Access-Token zurückgegeben.")
    credentials["access_token"] = access_token
    credentials["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    credential_store.save(sender, credentials)
    return access_token


def _access_token(
    credentials: dict[str, Any],
    credential_store: CredentialStore,
    sender: str,
    force_refresh: bool = False,
) -> str:
    if not credentials_have_required_scopes(credentials):
        raise AuthenticationRequiredError(
            "Gespeicherte OAuth-Daten enthalten nicht gmail.send und gmail.readonly. "
            "Führe 'auth' erneut aus."
        )
    if not force_refresh and credentials.get("access_token") and float(credentials.get("expires_at", 0)) > time.time() + 60:
        return str(credentials["access_token"])
    return _refresh(credentials, credential_store, sender)


def _gmail_request(
    credential_store: CredentialStore,
    sender: str,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    credentials = credential_store.load(sender)
    if str(credentials.get("sender", "")).casefold() != sender.casefold():
        raise AuthenticationRequiredError("OAuth-Daten wurden für einen anderen Absender eingerichtet.")

    for attempt in range(2):
        token = _access_token(
            credentials, credential_store, sender, force_refresh=attempt == 1
        )
        try:
            headers = {"Authorization": f"Bearer {token}"}
            if method == "GET":
                return _json_get(url, headers)
            if method == "POST" and payload is not None:
                return _json_post(url, payload, headers)
            raise AssertionError(f"Nicht unterstützte Gmail-Methode: {method}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401 and attempt == 0:
                continue
            if exc.code in {401, 403}:
                raise PermanentSendError(
                    f"Gmail-Berechtigung verweigert ({exc.code}): {detail[:500]}"
                ) from exc
            if exc.code == 429 or exc.code >= 500:
                raise TemporarySendError(
                    f"Gmail vorübergehend nicht verfügbar ({exc.code}): {detail[:500]}"
                ) from exc
            raise PermanentSendError(
                f"Gmail-Anfrage abgelehnt ({exc.code}): {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TemporarySendError(f"Gmail API ist nicht erreichbar: {exc.reason}") from exc
    raise PermanentSendError("Gmail-Autorisierung konnte nicht erneuert werden.")


def build_message(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    attachment: Path,
    message_id: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    if message_id:
        message["Message-ID"] = message_id
    message.set_content(body)
    message.add_attachment(
        attachment.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=attachment.name,
    )
    return message


def deterministic_message_id(invoice_id: str, pdf_sha256: str, sender: str) -> str:
    digest = hashlib.sha256(f"{invoice_id}\0{pdf_sha256}".encode("utf-8")).hexdigest()[:40]
    domain = sender.rsplit("@", 1)[-1].casefold() if "@" in sender else "localhost.invalid"
    return f"<chatgpt-invoice-{digest}@{domain}>"


def _header_values(metadata: dict[str, Any]) -> dict[str, str]:
    headers = metadata.get("payload", {}).get("headers", [])
    return {
        str(item.get("name", "")).casefold(): str(item.get("value", ""))
        for item in headers
        if isinstance(item, dict)
    }


def _contains_address(value: str, expected: str) -> bool:
    return expected.casefold() in {address.casefold() for _, address in getaddresses([value])}


def _find_sent_candidate(
    credential_store: CredentialStore,
    sender: str,
    query: str,
) -> dict[str, Any] | None:
    parameters = urllib.parse.urlencode(
        {"labelIds": "SENT", "q": query, "maxResults": "2"}
    )
    result = _gmail_request(
        credential_store, sender, "GET", f"{GMAIL_MESSAGES_ENDPOINT}?{parameters}"
    )
    messages = result.get("messages", [])
    if not isinstance(messages, list):
        raise TemporarySendError("Gmail lieferte eine ungültige Antwort für den Gesendet-Ordner.")
    if len(messages) > 1:
        raise PermanentSendError(
            "Gmail-Suche im Gesendet-Ordner ist mehrdeutig; Versand wurde vorsorglich gestoppt."
        )
    if not messages:
        return None
    message_id = str(messages[0].get("id", ""))
    if not message_id:
        raise TemporarySendError("Gmail-Suche lieferte keine Nachrichten-ID.")
    metadata_parameters = urllib.parse.urlencode(
        [
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Message-ID"),
        ]
    )
    return _gmail_request(
        credential_store,
        sender,
        "GET",
        f"{GMAIL_MESSAGES_ENDPOINT}/{urllib.parse.quote(message_id)}?{metadata_parameters}",
    )


def find_sent_message(
    credential_store: CredentialStore,
    sender: str,
    recipient: str,
    subject: str,
    message_id: str,
) -> str | None:
    by_id = _find_sent_candidate(
        credential_store, sender, f"in:sent rfc822msgid:{message_id}"
    )
    if by_id is not None:
        headers = _header_values(by_id)
        if headers.get("message-id", "").casefold() != message_id.casefold():
            raise PermanentSendError("Gmail-Treffer hat eine unerwartete Message-ID.")
        return str(by_id.get("id", ""))

    escaped_subject = subject.replace("\\", "\\\\").replace('"', '\\"')
    legacy_query = (
        f'in:sent from:{sender} to:{recipient} subject:"{escaped_subject}"'
    )
    legacy = _find_sent_candidate(credential_store, sender, legacy_query)
    if legacy is None:
        return None
    headers = _header_values(legacy)
    if (
        headers.get("subject") != subject
        or not _contains_address(headers.get("from", ""), sender)
        or not _contains_address(headers.get("to", ""), recipient)
    ):
        raise PermanentSendError(
            "Gmail-Treffer im Gesendet-Ordner stimmt nicht eindeutig mit der Rechnung überein."
        )
    return str(legacy.get("id", ""))


def send_message(
    credential_store: CredentialStore, message: EmailMessage, sender: str
) -> str:
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    response = _gmail_request(
        credential_store,
        sender,
        "POST",
        GMAIL_SEND_ENDPOINT,
        {"raw": encoded},
    )
    gmail_message_id = str(response.get("id", ""))
    if not gmail_message_id:
        raise TemporarySendError("Gmail API lieferte keine Nachrichten-ID.")
    return gmail_message_id
