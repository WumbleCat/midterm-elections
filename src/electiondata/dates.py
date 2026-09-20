"""Date helpers: election calendar and normalization of source date formats."""

from __future__ import annotations

import datetime as dt

import pandas as pd


def general_election_date(year: int) -> dt.date:
    """First Tuesday after the first Monday in November."""
    first = dt.date(year, 11, 1)
    # weekday(): Monday=0 ... Sunday=6; first Monday on/after Nov 1
    first_monday = first + dt.timedelta(days=(7 - first.weekday()) % 7)
    return first_monday + dt.timedelta(days=1)


def parse_date(value: object, *, formats: tuple[str, ...] = ()) -> dt.date | None:
    """Parse many source date formats into a date (None when not parseable)."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in formats:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def month_start(year: int, month: int) -> dt.date:
    return dt.date(year, month, 1)


def bls_period_to_date(year: int | str, period: str) -> dt.date | None:
    """BLS API periods: M01..M12 (monthly), Q01..Q04, A01 (annual). Returns period start."""
    year = int(year)
    if period.startswith("M"):
        m = int(period[1:])
        if m == 13:  # annual average
            return None
        return dt.date(year, m, 1)
    if period.startswith("Q"):
        q = int(period[1:])
        if q == 5:
            return None
        return dt.date(year, 3 * (q - 1) + 1, 1)
    if period.startswith("A"):
        return dt.date(year, 1, 1)
    return None


def to_timestamp_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce").dt.normalize()
