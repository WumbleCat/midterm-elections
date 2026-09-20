"""Canonical U.S. state geography shared by every connector and transform.

One table, three identifiers: ``state_name``, ``state_abbr`` (USPS) and
``state_fips`` (two-digit, zero-padded string). Connectors must call
:func:`normalize_state` instead of maintaining their own mappings.

The architecture reserves room for finer geographies (congressional district,
county FIPS, precinct) through :class:`GeoLevel`; state-level is the core today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd


class GeoLevel(StrEnum):
    NATION = "nation"
    STATE = "state"
    CONGRESSIONAL_DISTRICT = "congressional_district"
    COUNTY = "county"
    PRECINCT = "precinct"


@dataclass(frozen=True)
class State:
    name: str
    abbr: str
    fips: str
    region: str  # Census region name
    division: str  # Census division name
    is_state: bool = True  # False for DC / territories


# (name, abbr, fips, region, division, is_state)
_STATES: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("Alabama", "AL", "01", "South", "East South Central", True),
    ("Alaska", "AK", "02", "West", "Pacific", True),
    ("Arizona", "AZ", "04", "West", "Mountain", True),
    ("Arkansas", "AR", "05", "South", "West South Central", True),
    ("California", "CA", "06", "West", "Pacific", True),
    ("Colorado", "CO", "08", "West", "Mountain", True),
    ("Connecticut", "CT", "09", "Northeast", "New England", True),
    ("Delaware", "DE", "10", "South", "South Atlantic", True),
    ("District of Columbia", "DC", "11", "South", "South Atlantic", False),
    ("Florida", "FL", "12", "South", "South Atlantic", True),
    ("Georgia", "GA", "13", "South", "South Atlantic", True),
    ("Hawaii", "HI", "15", "West", "Pacific", True),
    ("Idaho", "ID", "16", "West", "Mountain", True),
    ("Illinois", "IL", "17", "Midwest", "East North Central", True),
    ("Indiana", "IN", "18", "Midwest", "East North Central", True),
    ("Iowa", "IA", "19", "Midwest", "West North Central", True),
    ("Kansas", "KS", "20", "Midwest", "West North Central", True),
    ("Kentucky", "KY", "21", "South", "East South Central", True),
    ("Louisiana", "LA", "22", "South", "West South Central", True),
    ("Maine", "ME", "23", "Northeast", "New England", True),
    ("Maryland", "MD", "24", "South", "South Atlantic", True),
    ("Massachusetts", "MA", "25", "Northeast", "New England", True),
    ("Michigan", "MI", "26", "Midwest", "East North Central", True),
    ("Minnesota", "MN", "27", "Midwest", "West North Central", True),
    ("Mississippi", "MS", "28", "South", "East South Central", True),
    ("Missouri", "MO", "29", "Midwest", "West North Central", True),
    ("Montana", "MT", "30", "West", "Mountain", True),
    ("Nebraska", "NE", "31", "Midwest", "West North Central", True),
    ("Nevada", "NV", "32", "West", "Mountain", True),
    ("New Hampshire", "NH", "33", "Northeast", "New England", True),
    ("New Jersey", "NJ", "34", "Northeast", "Middle Atlantic", True),
    ("New Mexico", "NM", "35", "West", "Mountain", True),
    ("New York", "NY", "36", "Northeast", "Middle Atlantic", True),
    ("North Carolina", "NC", "37", "South", "South Atlantic", True),
    ("North Dakota", "ND", "38", "Midwest", "West North Central", True),
    ("Ohio", "OH", "39", "Midwest", "East North Central", True),
    ("Oklahoma", "OK", "40", "South", "West South Central", True),
    ("Oregon", "OR", "41", "West", "Pacific", True),
    ("Pennsylvania", "PA", "42", "Northeast", "Middle Atlantic", True),
    ("Rhode Island", "RI", "44", "Northeast", "New England", True),
    ("South Carolina", "SC", "45", "South", "South Atlantic", True),
    ("South Dakota", "SD", "46", "Midwest", "West North Central", True),
    ("Tennessee", "TN", "47", "South", "East South Central", True),
    ("Texas", "TX", "48", "South", "West South Central", True),
    ("Utah", "UT", "49", "West", "Mountain", True),
    ("Vermont", "VT", "50", "Northeast", "New England", True),
    ("Virginia", "VA", "51", "South", "South Atlantic", True),
    ("Washington", "WA", "53", "West", "Pacific", True),
    ("West Virginia", "WV", "54", "South", "South Atlantic", True),
    ("Wisconsin", "WI", "55", "Midwest", "East North Central", True),
    ("Wyoming", "WY", "56", "West", "Mountain", True),
    ("Puerto Rico", "PR", "72", "Territory", "Territory", False),
    ("Guam", "GU", "66", "Territory", "Territory", False),
    ("U.S. Virgin Islands", "VI", "78", "Territory", "Territory", False),
    ("American Samoa", "AS", "60", "Territory", "Territory", False),
    ("Northern Mariana Islands", "MP", "69", "Territory", "Territory", False),
)

STATES: tuple[State, ...] = tuple(State(*row) for row in _STATES)
STATE_BY_ABBR: dict[str, State] = {s.abbr: s for s in STATES}
STATE_BY_FIPS: dict[str, State] = {s.fips: s for s in STATES}
STATE_BY_NAME: dict[str, State] = {s.name.upper(): s for s in STATES}

# Common aliases seen in source files.
_ALIASES: dict[str, str] = {
    "WASHINGTON DC": "DC",
    "WASHINGTON D.C.": "DC",
    "WASHINGTON, D.C.": "DC",
    "D.C.": "DC",
    "DISTRICT OF COLUMBIA": "DC",
    "US VIRGIN ISLANDS": "VI",
    "VIRGIN ISLANDS": "VI",
    "U.S. VIRGIN ISLANDS": "VI",
    "NORTHERN MARIANAS": "MP",
    "COMMONWEALTH OF THE NORTHERN MARIANA ISLANDS": "MP",
    "UNITED STATES": "US",
    "US": "US",
    "USA": "US",
    "NATIONAL": "US",
}

# 50 states + DC: the modelling universe for federal elections.
FIFTY_STATES_DC: tuple[str, ...] = tuple(s.abbr for s in STATES if s.is_state or s.abbr == "DC")
FIFTY_STATES: tuple[str, ...] = tuple(s.abbr for s in STATES if s.is_state)


def _normalize_token(value: object) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_state(value: object, *, allow_national: bool = False) -> str | None:
    """Return the USPS abbreviation for a state given a name, abbreviation or FIPS code.

    Returns ``None`` when the value cannot be mapped (callers decide whether that
    is an error). ``"US"`` is returned for national aggregates only when
    ``allow_national`` is True.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, int | float):
        fips = f"{int(value):02d}"
        return STATE_BY_FIPS[fips].abbr if fips in STATE_BY_FIPS else None
    text = _normalize_token(value)
    if not text or text in {"NAN", "NONE", "NULL"}:
        return None
    if text.isdigit():
        fips = f"{int(text):02d}"
        st = STATE_BY_FIPS.get(fips)
        return st.abbr if st else None
    if text in STATE_BY_ABBR:
        return text
    if text in STATE_BY_NAME:
        return STATE_BY_NAME[text].abbr
    alias = _ALIASES.get(text)
    if alias == "US":
        return "US" if allow_national else None
    if alias:
        return alias
    return None


def state_fips(value: object) -> str | None:
    abbr = normalize_state(value)
    return STATE_BY_ABBR[abbr].fips if abbr else None


def state_name(value: object) -> str | None:
    abbr = normalize_state(value)
    return STATE_BY_ABBR[abbr].name if abbr else None


def is_valid_state(value: object) -> bool:
    return normalize_state(value) is not None


def states_frame(include_territories: bool = False) -> pd.DataFrame:
    rows = [
        {
            "state_name": s.name,
            "state": s.abbr,
            "state_fips": s.fips,
            "census_region": s.region,
            "census_division": s.division,
            "is_state": s.is_state,
        }
        for s in STATES
        if include_territories or s.is_state or s.abbr == "DC"
    ]
    return pd.DataFrame(rows)


def add_state_columns(
    df: pd.DataFrame, source_col: str, *, drop_unmapped: bool = False
) -> pd.DataFrame:
    """Add canonical ``state``/``state_fips``/``state_name`` from ``source_col``.

    Unmapped values are kept (with nulls) unless ``drop_unmapped`` is True so that
    validation can report them rather than silently losing rows.
    """
    out = df.copy()
    out["state"] = out[source_col].map(normalize_state)
    out["state_fips"] = out["state"].map(
        lambda a: STATE_BY_ABBR[a].fips if a in STATE_BY_ABBR else None
    )
    out["state_name"] = out["state"].map(
        lambda a: STATE_BY_ABBR[a].name if a in STATE_BY_ABBR else None
    )
    if drop_unmapped:
        out = out[out["state"].notna()]
    return out
