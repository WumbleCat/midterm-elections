"""Canonical party normalization shared by every source.

The original label is always preserved in ``party_raw``; ``party`` holds one of
``DEM | REP | LIB | GRN | IND | OTHER``.
"""

from __future__ import annotations

import re

import pandas as pd

CANONICAL_PARTIES = ("DEM", "REP", "LIB", "GRN", "IND", "OTHER")

_EXACT: dict[str, str] = {
    # MEDSL / common labels
    "DEMOCRAT": "DEM",
    "DEMOCRATIC": "DEM",
    "DEMOCRATIC PARTY": "DEM",
    "DEMOCRATIC-FARMER-LABOR": "DEM",
    "DEMOCRATIC-NONPARTISAN LEAGUE": "DEM",
    "DEMOCRATIC-NPL": "DEM",
    "REPUBLICAN": "REP",
    "REPUBLICAN PARTY": "REP",
    "LIBERTARIAN": "LIB",
    "LIBERTARIAN PARTY": "LIB",
    "GREEN": "GRN",
    "GREEN PARTY": "GRN",
    "PACIFIC GREEN": "GRN",
    "INDEPENDENT": "IND",
    "INDEPENDENCE": "IND",
    "NONPARTISAN": "IND",
    "NO PARTY AFFILIATION": "IND",
    "NO PARTY PREFERENCE": "IND",
    "UNAFFILIATED": "IND",
    "UNENROLLED": "IND",
    # FEC codes
    "DEM": "DEM",
    "REP": "REP",
    "LIB": "LIB",
    "GRE": "GRN",
    "GRN": "GRN",
    "IND": "IND",
    "NPA": "IND",
    "NNE": "IND",
    "NON": "IND",
    "UNK": "OTHER",
    "DFL": "DEM",
    "DNL": "DEM",
    "OTH": "OTHER",
    "OTHER": "OTHER",
}

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^DEMOCRAT"), "DEM"),
    (re.compile(r"^REPUBLICAN"), "REP"),
    (re.compile(r"^LIBERTARIAN"), "LIB"),
    (re.compile(r"\bGREEN\b"), "GRN"),
    (re.compile(r"^INDEPENDENT$"), "IND"),
)


def normalize_party(value: object) -> str:
    """Map a party label/code to a canonical party. Unknown -> OTHER, missing -> OTHER."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return "OTHER"
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    if not text:
        return "OTHER"
    if text in _EXACT:
        return _EXACT[text]
    for pattern, party in _PATTERNS:
        if pattern.search(text):
            return party
    return "OTHER"


def normalize_party_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_party)
