from __future__ import annotations

from datetime import date, timedelta


def allowed_send_dates(invoice_date: date, retry_offsets_days: tuple[int, ...]) -> tuple[date, ...]:
    return tuple(invoice_date + timedelta(days=offset) for offset in retry_offsets_days)


def is_send_day(today: date, invoice_date: date, retry_offsets_days: tuple[int, ...]) -> bool:
    return today in allowed_send_dates(invoice_date, retry_offsets_days)


def is_scheduled_calendar_day(today: date, billing_day: int, retry_offsets_days: tuple[int, ...]) -> bool:
    expected_invoice_date = date(today.year, today.month, billing_day)
    return today in allowed_send_dates(expected_invoice_date, retry_offsets_days)

