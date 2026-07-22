from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from chatgpt_invoice_agent.errors import ValidationError
from chatgpt_invoice_agent.pdf_validation import validate_invoice_pdf


class PdfValidationTests(unittest.TestCase):
    def _write_pdf(self, path: Path, title: str) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_metadata({"/Title": title})
        with path.open("wb") as handle:
            writer.write(handle)

    def test_valid_invoice_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invoice.pdf"
            self._write_pdf(path, "OpenAI Rechnung 3. Juli 2026 UWYGIGUK-0002")
            result = validate_invoice_pdf(path, date(2026, 7, 3), "UWYGIGUK-0002")
            self.assertEqual(result.page_count, 1)
            self.assertEqual(len(result.sha256), 64)

    def test_invoice_number_with_pdf_null_separator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invoice.pdf"
            self._write_pdf(path, "OpenAI Invoice July 3, 2026 UWYGIGUK\x000002")
            result = validate_invoice_pdf(path, date(2026, 7, 3), "UWYGIGUK-0002")
            self.assertEqual(result.page_count, 1)

    def test_wrong_issuer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invoice.pdf"
            self._write_pdf(path, "Other Vendor 3. Juli 2026 INV-2")
            with self.assertRaises(ValidationError):
                validate_invoice_pdf(path, date(2026, 7, 3), "INV-2")


if __name__ == "__main__":
    unittest.main()
