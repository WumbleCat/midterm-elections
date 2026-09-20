import datetime as dt

import pandas as pd
import pytest

from electiondata.dates import bls_period_to_date, general_election_date, parse_date
from electiondata.geo import (
    FIFTY_STATES,
    FIFTY_STATES_DC,
    add_state_columns,
    normalize_state,
    state_fips,
    state_name,
    states_frame,
)
from electiondata.parties import normalize_party


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PA", "PA"),
        ("pa", "PA"),
        ("Pennsylvania", "PA"),
        ("PENNSYLVANIA", "PA"),
        ("42", "PA"),
        ("042", "PA"),
        (42, "PA"),
        (42.0, "PA"),
        ("District of Columbia", "DC"),
        ("Washington DC", "DC"),
        ("11", "DC"),
        ("Puerto Rico", "PR"),
        ("  new york ", "NY"),
        ("Narnia", None),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_normalize_state(value, expected):
    assert normalize_state(value) == expected


def test_national_only_when_allowed():
    assert normalize_state("United States") is None
    assert normalize_state("United States", allow_national=True) == "US"


def test_fips_and_name_roundtrip():
    assert state_fips("Pennsylvania") == "42"
    assert state_name("42") == "Pennsylvania"
    assert len(FIFTY_STATES) == 50
    assert len(FIFTY_STATES_DC) == 51
    frame = states_frame()
    assert set(frame["state"]) == set(FIFTY_STATES_DC)
    assert frame["state_fips"].str.len().eq(2).all()


def test_add_state_columns_keeps_unmapped_rows():
    df = pd.DataFrame({"st": ["PA", "Nowhere", "10"]})
    out = add_state_columns(df, "st")
    assert out["state"].fillna("?").tolist() == ["PA", "?", "DE"]
    assert out["state_fips"].fillna("?").tolist() == ["42", "?", "10"]
    assert len(add_state_columns(df, "st", drop_unmapped=True)) == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DEMOCRAT", "DEM"),
        ("Democratic-Farmer-Labor", "DEM"),
        ("REPUBLICAN", "REP"),
        ("LIBERTARIAN", "LIB"),
        ("GREEN", "GRN"),
        ("Pacific Green", "GRN"),
        ("INDEPENDENT", "IND"),
        ("WORKING FAMILIES", "OTHER"),
        ("DEM", "DEM"),
        ("REP", "REP"),
        ("GRE", "GRN"),
        ("NPA", "IND"),
        ("DFL", "DEM"),
        ("", "OTHER"),
        (None, "OTHER"),
    ],
)
def test_normalize_party(raw, expected):
    assert normalize_party(raw) == expected


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2020, dt.date(2020, 11, 3)),
        (2022, dt.date(2022, 11, 8)),
        (2024, dt.date(2024, 11, 5)),
        (2026, dt.date(2026, 11, 3)),
        (2016, dt.date(2016, 11, 8)),
    ],
)
def test_general_election_date(year, expected):
    assert general_election_date(year) == expected


def test_parse_date_formats():
    assert parse_date("12/31/2024", formats=("%m/%d/%Y",)) == dt.date(2024, 12, 31)
    assert parse_date("2024-10-15") == dt.date(2024, 10, 15)
    assert parse_date("not a date") is None
    assert parse_date(None) is None
    assert parse_date(pd.Timestamp("2020-01-02")) == dt.date(2020, 1, 2)


def test_bls_periods():
    assert bls_period_to_date(2024, "M03") == dt.date(2024, 3, 1)
    assert bls_period_to_date("2024", "M13") is None
    assert bls_period_to_date(2024, "Q02") == dt.date(2024, 4, 1)
    assert bls_period_to_date(2024, "A01") == dt.date(2024, 1, 1)
