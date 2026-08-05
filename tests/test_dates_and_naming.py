from __future__ import annotations

import unittest
from datetime import date

from chatgpt_invoice_agent.dates import (
    allowed_send_dates,
    first_send_date,
    is_scheduled_calendar_day,
    is_send_day,
)
from chatgpt_invoice_agent.naming import invoice_filename, safe_component, safe_person_component


class DatesAndNamingTests(unittest.TestCase):
    def test_sending_stays_eligible_after_first_retry_day(self) -> None:
        invoice_date = date(2026, 8, 3)
        self.assertEqual(
            allowed_send_dates(invoice_date, (1, 2, 3)),
            (date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6)),
        )
        self.assertEqual(first_send_date(invoice_date, (1, 2, 3)), date(2026, 8, 4))
        self.assertTrue(is_send_day(date(2026, 8, 4), invoice_date, (1, 2, 3)))
        self.assertTrue(is_send_day(date(2026, 8, 7), invoice_date, (1, 2, 3)))
        self.assertFalse(is_send_day(date(2026, 8, 3), invoice_date, (1, 2, 3)))

    def test_scheduled_calendar_days_remain_open_after_first_day(self) -> None:
        self.assertTrue(is_scheduled_calendar_day(date(2026, 8, 6), 3, (1, 2, 3)))
        self.assertTrue(is_scheduled_calendar_day(date(2026, 8, 20), 3, (1, 2, 3)))
        self.assertFalse(is_scheduled_calendar_day(date(2026, 8, 3), 3, (1, 2, 3)))

    def test_windows_safe_filename(self) -> None:
        self.assertEqual(safe_component(' RAIVA: Technologies / GmbH* '), "RAIVA-Technologies-GmbH")
        self.assertEqual(
            invoice_filename('Niels Welsch', date(2026, 7, 3)),
            "Rechnung_CHATGPT_Niels_Welsch_072026.pdf",
        )
        self.assertEqual(safe_component("CON"), "_CON")
        self.assertEqual(safe_person_component(" Niels/Welsch "), "Niels_Welsch")


if __name__ == "__main__":
    unittest.main()
