from __future__ import annotations

import tempfile
import unittest
import io
import urllib.error
from pathlib import Path
from unittest.mock import patch

from chatgpt_invoice_agent.gmail_api import (
    REQUIRED_GMAIL_SCOPES,
    build_message,
    credentials_have_required_scopes,
    deterministic_message_id,
    find_sent_message,
    _gmail_request,
    send_message,
)
from chatgpt_invoice_agent.errors import AuthenticationRequiredError, PermanentSendError


class FakeCredentialStore:
    backend_name = "fake"

    def __init__(self, credentials: dict[str, object]):
        self.credentials = credentials

    def exists(self, sender: str) -> bool:
        return True

    def load(self, sender: str) -> dict[str, object]:
        return dict(self.credentials)

    def save(self, sender: str, payload: dict[str, object]) -> None:
        self.credentials = dict(payload)


class GmailApiTests(unittest.TestCase):
    def test_message_and_send_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            attachment = Path(directory) / "invoice.pdf"
            attachment.write_bytes(b"%PDF-test")
            message = build_message(
                "Niels.Welsch@raiva.io",
                "Niels.Welsch@raiva.io",
                "ChatGPT-Rechnung – Example – 03.07.2026",
                "Anbei die Rechnung.",
                attachment,
                message_id="<chatgpt-invoice-test@raiva.io>",
            )
            self.assertEqual(message["From"], "Niels.Welsch@raiva.io")
            self.assertEqual(message["To"], "Niels.Welsch@raiva.io")
            self.assertEqual(message["Message-ID"], "<chatgpt-invoice-test@raiva.io>")
            attachments = list(message.iter_attachments())
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0].get_filename(), "invoice.pdf")

            credentials = {
                "version": 2,
                "sender": "Niels.Welsch@raiva.io",
                "scopes": list(REQUIRED_GMAIL_SCOPES),
                "access_token": "redacted",
                "expires_at": 9999999999,
            }
            store = FakeCredentialStore(credentials)
            with patch(
                "chatgpt_invoice_agent.gmail_api._json_post", return_value={"id": "gmail-123"}
            ) as post:
                result = send_message(store, message, "Niels.Welsch@raiva.io")
            self.assertEqual(result, "gmail-123")
            self.assertEqual(post.call_count, 1)
            self.assertIn("raw", post.call_args.args[1])

    def test_version_one_credentials_require_reauthorization(self) -> None:
        self.assertFalse(
            credentials_have_required_scopes(
                {"version": 1, "scope": "https://www.googleapis.com/auth/gmail.send"}
            )
        )
        self.assertTrue(
            credentials_have_required_scopes(
                {"version": 2, "scopes": list(REQUIRED_GMAIL_SCOPES)}
            )
        )
        legacy_store = FakeCredentialStore(
            {
                "version": 1,
                "sender": "sender@example.com",
                "scope": "https://www.googleapis.com/auth/gmail.send",
                "access_token": "legacy",
                "expires_at": 9999999999,
            }
        )
        message = build_message(
            "sender@example.com",
            "recipient@example.com",
            "Invoice subject",
            "Body",
            Path(__file__),
        )
        with (
            patch("chatgpt_invoice_agent.gmail_api._json_post") as post,
            self.assertRaises(AuthenticationRequiredError),
        ):
            send_message(legacy_store, message, "sender@example.com")
        post.assert_not_called()

    def test_deterministic_message_id_has_rfc_safe_local_part(self) -> None:
        first = deterministic_message_id("INV-1", "a" * 64, "sender@example.com")
        second = deterministic_message_id("INV-1", "a" * 64, "sender@example.com")
        self.assertEqual(first, second)
        self.assertLessEqual(len(first.strip("<>").split("@", 1)[0]), 64)

    def test_sent_message_is_found_by_deterministic_message_id(self) -> None:
        store = FakeCredentialStore({})
        message_id = deterministic_message_id("INV-1", "abc", "sender@example.com")
        responses = [
            {"messages": [{"id": "gmail-123"}]},
            {
                "id": "gmail-123",
                "labelIds": ["SENT"],
                "payload": {"headers": [{"name": "Message-ID", "value": message_id}]},
            },
        ]
        with patch(
            "chatgpt_invoice_agent.gmail_api._gmail_request", side_effect=responses
        ) as request:
            found = find_sent_message(
                store,
                "sender@example.com",
                "recipient@example.com",
                "Invoice subject",
                message_id,
            )
        self.assertEqual(found, "gmail-123")
        self.assertEqual(request.call_count, 2)

    def test_legacy_sent_message_is_confirmed_by_headers(self) -> None:
        store = FakeCredentialStore({})
        responses = [
            {"messages": []},
            {"messages": [{"id": "legacy-1"}]},
            {
                "id": "legacy-1",
                "labelIds": ["SENT"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@example.com"},
                        {"name": "Subject", "value": "Invoice subject"},
                    ]
                },
            },
        ]
        with patch(
            "chatgpt_invoice_agent.gmail_api._gmail_request", side_effect=responses
        ):
            found = find_sent_message(
                store,
                "sender@example.com",
                "recipient@example.com",
                "Invoice subject",
                "<new-id@example.com>",
            )
        self.assertEqual(found, "legacy-1")

    def test_ambiguous_sent_search_stops_before_send(self) -> None:
        store = FakeCredentialStore({})
        with patch(
            "chatgpt_invoice_agent.gmail_api._gmail_request",
            return_value={"messages": [{"id": "one"}, {"id": "two"}]},
        ):
            with self.assertRaises(PermanentSendError):
                find_sent_message(
                    store,
                    "sender@example.com",
                    "recipient@example.com",
                    "Invoice subject",
                    "<message-id@example.com>",
                )

    def test_unauthorized_lookup_refreshes_token_once(self) -> None:
        credentials = {
            "version": 2,
            "sender": "sender@example.com",
            "scopes": list(REQUIRED_GMAIL_SCOPES),
            "access_token": "expired",
            "expires_at": 9999999999,
            "client_id": "client",
            "client_secret": "secret",
            "refresh_token": "refresh",
            "token_uri": "https://accounts.example/token",
        }
        store = FakeCredentialStore(credentials)
        unauthorized = urllib.error.HTTPError(
            "https://gmail.example/messages",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"expired"}'),
        )
        with (
            patch(
                "chatgpt_invoice_agent.gmail_api._json_get",
                side_effect=[unauthorized, {"messages": []}],
            ) as get,
            patch(
                "chatgpt_invoice_agent.gmail_api._form_post",
                return_value={"access_token": "fresh", "expires_in": 3600},
            ),
        ):
            result = _gmail_request(
                store,
                "sender@example.com",
                "GET",
                "https://gmail.example/messages",
            )
        self.assertEqual(result, {"messages": []})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(store.credentials["access_token"], "fresh")


if __name__ == "__main__":
    unittest.main()
