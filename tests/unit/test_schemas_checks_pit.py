import datetime as dt

import pandas as pd
import pytest

from electiondata.exceptions import NormalizationError, PointInTimeError
from electiondata.quality import release_calendar
from electiondata.quality.checks import audit_frame, compare_row_counts, validate_table
from electiondata.quality.point_in_time import (
    assert_no_future_rows,
    filter_as_of,
    latest_as_of,
    leakage_report,
)
from electiondata.quality.schemas import SCHEMAS, empty_frame, enforce_schema, get_schema


def _prov(n: int, pub: list[str] | None = None) -> dict:
    return {
        "observation_date": ["2024-01-01"] * n,
        "publication_date": pub or ["2024-02-01"] * n,
        "publication_date_estimated": [False] * n,
        "retrieval_date": ["2026-09-20"] * n,
        "source": ["TEST"] * n,
        "dataset_id": ["test"] * n,
        "ingestion_run_id": ["r1"] * n,
    }


def test_schema_registry_has_expected_tables():
    for name in (
        "election_results",
        "turnout",
        "demographics",
        "labor",
        "industry",
        "state_economy",
        "candidates",
        "candidate_finance",
        "polls",
        "religion",
        "naep",
        "individual_turnout_cps",
        "individual_behavior_anes",
    ):
        assert name in SCHEMAS
    with pytest.raises(NormalizationError):
        get_schema("nope")


def test_enforce_schema_casts_and_orders():
    df = pd.DataFrame(
        {
            "state": ["PA"],
            "state_fips": ["42"],
            "year": ["2024"],
            "land_area_sq_miles": ["44742.1"],
            **_prov(1),
        }
    )
    out = enforce_schema(df, SCHEMAS["geography"])
    assert list(out.columns) == SCHEMAS["geography"].column_names
    assert str(out["year"].dtype) == "Int64"
    assert str(out["land_area_sq_miles"].dtype) == "Float64"
    assert out["water_area_sq_miles"].isna().all()  # missing nullable column added
    assert pd.api.types.is_datetime64_any_dtype(out["publication_date"])


def test_enforce_schema_missing_required_raises():
    df = pd.DataFrame({"state": ["PA"], **_prov(1)})  # no state_fips/year
    with pytest.raises(NormalizationError):
        enforce_schema(df, SCHEMAS["geography"])
    assert enforce_schema(df, SCHEMAS["geography"], strict=False).shape[0] == 1
    assert empty_frame(SCHEMAS["turnout"]).empty


def test_validation_rules_flag_problems():
    df = pd.DataFrame(
        {
            "state": ["PA", "PA", "ZZ"],
            "state_fips": ["42", "42", "99"],
            "year": [2024, 2024, 2024],
            "office": ["senate"] * 3,
            "district": ["statewide"] * 3,
            "special": [False] * 3,
            "dem_votes": [10.0, 10.0, -5.0],
            "rep_votes": [5.0, 5.0, 5.0],
            "other_votes": [1.0, 1.0, 0.0],
            "total_candidate_votes": [16.0, 16.0, 999.0],
            "total_votes": [16.0, 16.0, 999.0],
            "dem_two_party_share": [0.66, 0.66, 1.5],
            "winner_party": ["DEM", "DEM", "XYZ"],
            **_prov(3),
        }
    )
    report = validate_table("election_race_summary", df, dataset="t", source="T")
    rules = {i.rule for i in report.issues}
    assert "duplicate_key" in rules
    assert "invalid_state" in rules
    assert "share_out_of_range" in rules
    assert "negative_count" in rules
    assert "vote_components_mismatch" in rules
    assert not report.ok
    issue = next(i for i in report.issues if i.rule == "duplicate_key")
    assert (
        issue.table == "election_race_summary"
        and issue.dataset == "t"
        and issue.source == "T"
        and issue.field
    )
    frame = report.to_frame()
    assert {"table", "dataset", "source", "rule", "field", "record"} <= set(frame.columns)


def test_validation_clean_frame_ok():
    df = pd.DataFrame(
        {
            "state": ["PA"],
            "state_fips": ["42"],
            "year": [2024],
            "land_area_sq_miles": [1.0],
            **_prov(1),
        }
    )
    report = validate_table("geography", enforce_schema(df, SCHEMAS["geography"]))
    assert report.ok and not report.warnings


def test_percent_units_documented():
    assert SCHEMAS["labor"].column("unemployment_rate").unit == "percent 0-100"
    assert SCHEMAS["demographics"].column("pct_bachelors").unit == "share 0-1"


def test_row_count_comparison():
    assert compare_row_counts(None, 10) is None
    assert compare_row_counts(100, 105) is None
    assert "changed" in compare_row_counts(100, 40)


def test_audit_frame():
    df = pd.DataFrame(
        {
            "state": ["PA", "PA"],
            "state_fips": ["42", "42"],
            "year": [2024, 2024],
            "land_area_sq_miles": [1.0, None],
            **_prov(2),
        }
    )
    out = audit_frame(df, "geography")
    assert out["rows"] == 2 and out["duplicate_key_rows"] == 2 and out["states"] == 1


# ------------------------------------------------------------- point in time


def test_filter_as_of_basic():
    df = pd.DataFrame({"v": [1, 2, 3], "publication_date": ["2024-01-01", "2024-06-01", None]})
    out = filter_as_of(df, "2024-03-01")
    assert out["v"].tolist() == [1]
    assert filter_as_of(df, "2024-03-01", keep_unknown=True)["v"].tolist() == [1, 3]
    assert filter_as_of(df, None) is df
    assert filter_as_of(df, dt.date(2024, 12, 31))["v"].tolist() == [1, 2]


def test_filter_as_of_without_publication_dates():
    df = pd.DataFrame({"v": [1]})
    with pytest.raises(PointInTimeError):
        filter_as_of(df, "2024-01-01")
    assert len(filter_as_of(df, "2024-01-01", strict=False)) == 1
    df2 = pd.DataFrame({"v": [1, 2], "retrieval_date": ["2023-01-01", "2025-01-01"]})
    assert filter_as_of(df2, "2024-01-01")["v"].tolist() == [1]


def test_latest_as_of_prefers_vintage_available_at_the_time():
    df = pd.DataFrame(
        {
            "state": ["PA"] * 3,
            "year": [2022, 2022, 2023],
            "population": [100, 101, 105],
            "revision_vintage": ["2022", "2023", "2023"],
            "observation_date": ["2022-07-01", "2022-07-01", "2023-07-01"],
            "publication_date": ["2022-12-31", "2023-12-31", "2023-12-31"],
        }
    )
    out = latest_as_of(df, "2023-06-01", keys=["state"], order_col="year")
    assert out["population"].tolist() == [100]  # only the 2022 vintage existed
    out = latest_as_of(df, "2024-06-01", keys=["state"], order_col="year")
    assert out["population"].tolist() == [105]


def test_assert_no_future_rows_and_report():
    df = pd.DataFrame(
        {
            "publication_date": ["2024-01-01", "2024-12-01"],
            "publication_date_estimated": [True, False],
        }
    )
    with pytest.raises(PointInTimeError):
        assert_no_future_rows(df, "2024-06-01")
    assert_no_future_rows(df, "2025-01-01")
    rep = leakage_report(df, "2024-06-01")
    assert (
        rep["rows_after_as_of"] == 1
        and rep["rows_available"] == 1
        and rep["estimated_publication_rows"] == 1
    )


def test_release_calendar_rules():
    assert release_calendar.bls_laus_state(dt.date(2024, 8, 1)) == dt.date(2024, 9, 21)
    assert release_calendar.bls_cpi(dt.date(2024, 9, 15)) == dt.date(2024, 10, 15)
    assert release_calendar.acs_1year(2023) == dt.date(2024, 9, 30)
    assert release_calendar.pep_vintage(2024) == dt.date(2024, 12, 31)
    assert release_calendar.naep(2022) == dt.date(2022, 12, 31)
    assert release_calendar.naep(2024) == dt.date(2025, 6, 30)
    assert release_calendar.from_url_month_folder(
        "https://www.eac.gov/sites/default/files/2023-06/x.zip"
    ) == dt.date(2023, 6, 30)
    assert release_calendar.from_url_month_folder("https://example.org/x.zip") is None
