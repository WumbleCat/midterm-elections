"""Publication-date rules for sources that do not ship a release date per row.

Every estimate produced here MUST be stored with ``publication_date_estimated=True``
so downstream users can see that the point-in-time cut relies on a documented
release-lag rule rather than a recorded release date. Rules are deliberately
conservative (they err on the side of *later* availability) so that a forecast
never sees data before it could really have existed.

Sources:
* BLS state LAUS: "Regional and State Employment and Unemployment" release,
  roughly 3 weeks after the reference month. Rule: month_end + 21 days.
* BLS CPI: released ~10-15 days after the reference month. Rule: month_end + 15.
* BLS CES/CPS national ("Employment Situation"): first Friday after the month.
  Rule: month_end + 8 days.
* BLS QCEW annual averages: published with Q4 data, ~6 months later. Rule: June 30 of year+1.
* Census ACS 1-year: mid-September of year+1. Rule: Sept 30 of year+1.
* Census ACS 5-year: early December of end-year+1. Rule: Dec 31 of year+1.
* Census PEP state totals (vintage V): released December of V. Rule: Dec 31 of V.
* Census Gazetteer / urban-rural: geography reference files. Rule: Dec 31 of the
  vintage year (2020 urban/rural criteria results were released Dec 2022 -> use 2022-12-31).
* EAC EAVS: taken from the month folder in the download URL (e.g. ``/files/2023-06/``).
* BEA annual state GDP / personal income: ~September of year+1 (comprehensive
  releases later). Rule: Sept 30 of year+1. RPP: Dec 31 of year+1.
* NAEP: national/state results released the autumn after the spring assessment.
  Rule: Dec 31 of the assessment year (2017 results came April 2018 and 2024
  results January 2025, so those vintages use the following year).
* FEC candidate financial summaries: quarterly reports are due 15 days after the
  coverage end (year-end reports Jan 31). Rule: coverage_end + 20 days.
* MEDSL results: unofficial totals are known on election night; the certified,
  cleaned dataset arrives months later. Rule: election_date (targets only) —
  when used as a *feature* for a later election this is always satisfied.
"""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd


def month_end(date: dt.date) -> dt.date:
    nxt = (date.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return nxt - dt.timedelta(days=1)


def bls_laus_state(period: dt.date) -> dt.date:
    return month_end(period) + dt.timedelta(days=21)


def bls_cpi(period: dt.date) -> dt.date:
    return month_end(period) + dt.timedelta(days=15)


def bls_employment_situation(period: dt.date) -> dt.date:
    return month_end(period) + dt.timedelta(days=8)


def bls_qcew_annual(year: int) -> dt.date:
    return dt.date(year + 1, 6, 30)


def acs_1year(year: int) -> dt.date:
    return dt.date(year + 1, 9, 30)


def acs_5year(end_year: int) -> dt.date:
    return dt.date(end_year + 1, 12, 31)


def pep_vintage(vintage: int) -> dt.date:
    return dt.date(vintage, 12, 31)


def census_geography(vintage: int) -> dt.date:
    return dt.date(vintage, 12, 31)


def urban_rural(census_year: int) -> dt.date:
    # 2020 criteria-based results were published in December 2022; 2010 in 2012.
    return dt.date(census_year + 2, 12, 31)


def bea_annual(year: int) -> dt.date:
    return dt.date(year + 1, 9, 30)


def bea_rpp(year: int) -> dt.date:
    return dt.date(year + 1, 12, 31)


_NAEP_NEXT_YEAR = {2017, 2024, 2009}


def naep(assessment_year: int) -> dt.date:
    if assessment_year in _NAEP_NEXT_YEAR:
        return dt.date(assessment_year + 1, 6, 30)
    return dt.date(assessment_year, 12, 31)


def fec_summary(coverage_end: dt.date) -> dt.date:
    return coverage_end + dt.timedelta(days=20)


_URL_MONTH = re.compile(r"/(\d{4})-(\d{2})/")


def from_url_month_folder(url: str) -> dt.date | None:
    """EAC posts files under ``/files/YYYY-MM/``; use the end of that month."""
    m = _URL_MONTH.search(url)
    if not m:
        return None
    return month_end(dt.date(int(m.group(1)), int(m.group(2)), 1))


def apply_rule(series: pd.Series, rule) -> pd.Series:  # noqa: ANN001
    """Vectorised helper: apply a date rule to a Series of dates/ints."""
    return series.map(lambda v: rule(v) if v is not None and not pd.isna(v) else None)
