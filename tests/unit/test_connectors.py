"""Connector parse tests on recorded excerpts of real files (offline)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from conftest import artifact_from_fixture
from electiondata.exceptions import AuthenticationError, DatasetUnavailableError, SchemaChangeError
from electiondata.ingestion.sources import bea, bls, census, eac, fec, medsl, naep, pew, polling
from electiondata.quality.checks import validate_table
from electiondata.quality.schemas import SCHEMAS, enforce_schema


def _finish(df: pd.DataFrame, table: str, ctx) -> pd.DataFrame:  # noqa: ANN001
    """Mimic the runner: add provenance and enforce the schema, then validate."""
    from electiondata.ingestion.runner import _add_provenance

    spec = next(
        s
        for s in __import__(
            "electiondata.ingestion.registry", fromlist=["REGISTRY"]
        ).REGISTRY.values()
        if s.normalized_table == table
    )
    out = enforce_schema(_add_provenance(df, spec, ctx, []), SCHEMAS[table])
    report = validate_table(table, out, dataset=spec.id)
    assert report.ok, [i.message for i in report.errors]
    return out


# ------------------------------------------------------------------ MEDSL


def test_medsl_senate_parse(ctx):
    art = artifact_from_fixture("medsl_senate_sample.csv", ctx, as_name="1976-2024-senate.csv")
    out = medsl.SenateResultsConnector().parse([art], ctx)
    out = _finish(out, "election_results", ctx)
    pa24 = out[(out.state == "PA") & (out.year == 2024)]
    assert set(pa24["party"]) >= {"DEM", "REP"}
    assert (out["election_type"] == "general").all()
    # NY fusion lines collapsed per candidate, party from the largest line
    ny = out[(out.state == "NY") & (out.year == 2022) & (out.candidate == "CHARLES E. SCHUMER")]
    assert (
        len(ny) == 1
        and ny.iloc[0]["party"] == "DEM"
        and "WORKING FAMILIES" in ny.iloc[0]["party_raw"]
    )
    # GA 2020 regular + special kept apart
    ga = out[(out.state == "GA") & (out.year == 2020)]
    assert ga["special"].nunique() == 2
    assert (out["publication_date"] == out["election_date"]).all()


def test_medsl_president_parse(ctx):
    art = artifact_from_fixture(
        "medsl_president_sample.csv", ctx, as_name="1976-2024-president.csv"
    )
    out = medsl.PresidentResultsConnector().parse([art], ctx)
    out = _finish(out, "election_results", ctx)
    assert (out["district"] == "statewide").all() and (out["office"] == "president").all()
    pa20 = out[(out.state == "PA") & (out.year == 2020)]
    assert pa20.set_index("party")["votes"].get("DEM") > pa20.set_index("party")["votes"].get("REP")


def test_medsl_house_layout_parse(ctx):
    art = artifact_from_fixture(
        "medsl_house_layout_fixture.tab", ctx, as_name="1976-2024-house.tab"
    )
    out = medsl.HouseResultsConnector().parse([art], ctx)
    out = _finish(out, "election_results", ctx)
    assert set(out["district"]) == {"01", "17", "at-large"}  # runoff row excluded
    wy = out[out.state == "WY"].set_index("candidate")["votes"]
    assert wy["HARRIET HAGEMAN"] == 132000  # vote modes summed when no TOTAL row
    ny = out[(out.state == "NY")]
    assert len(ny) == 2 and set(ny["party"]) == {"DEM", "REP"}


def test_medsl_schema_change_detected():
    with pytest.raises(SchemaChangeError):
        medsl.normalize_medsl(pd.DataFrame({"year": [2020]}), "senate", party_col="party_detailed")


def test_medsl_house_manual_missing(ctx):
    with pytest.raises(DatasetUnavailableError):
        medsl.HouseResultsConnector().fetch(ctx)


# -------------------------------------------------------------------- EAC


def test_eavs_parse(ctx):
    art = artifact_from_fixture(
        "eavs_2022_sample.zip", ctx, as_name="eavs_2022.zip", extra={"year": 2022}
    )
    art.url = eac.EAVS_FILES[2022]
    out = eac.EavsConnector().parse([art], ctx)
    out = _finish(out, "turnout", ctx)
    pa = out[out.state == "PA"].iloc[0]
    assert pa["ballots_cast"] == 5410022  # sum of jurisdictions (negatives treated as missing)
    assert pa["registered_voters"] == 8873144
    assert pa["publication_date"] == pd.Timestamp("2023-06-30")
    assert pa["revision_vintage"] == "V1"
    assert set(out["state"]) == {"PA", "DE", "VT"}
    assert (out["n_jurisdictions"] > 0).all()


def test_eavs_negative_codes_are_missing():
    df = pd.DataFrame({"State_Abbr": ["XX", "XX"], "A1a": ["10", "-99"], "F1a": ["-88", "5"]})
    with pytest.raises(SchemaChangeError):
        eac.normalize_eavs(df.drop(columns=["F1a"]), 2022)
    df["State_Abbr"] = "DE"
    out = eac.normalize_eavs(df, 2022)
    assert out.iloc[0]["registered_voters"] == 10 and out.iloc[0]["ballots_cast"] == 5
    assert out.iloc[0]["n_jurisdictions_missing_ballots"] == 1


# ----------------------------------------------------------------- Census


def test_pep_parse_multiple_vintages(ctx):
    arts = [
        artifact_from_fixture(f"pep_vintage_{v}.csv", ctx, extra={"vintage": v})
        for v in (2009, 2019, 2024)
    ]
    out = census.PepPopulationConnector().parse(arts, ctx)
    out = _finish(out, "population", ctx)
    pa = out[out.state == "PA"]
    assert set(pa["revision_vintage"]) == {"2009", "2019", "2024"}
    assert pa[pa.year == 2000]["population"].iloc[0] > 12_000_000
    assert (
        pa[pa.revision_vintage == "2024"]["publication_date"] == pd.Timestamp("2024-12-31")
    ).all()
    assert (
        pa[(pa.year == 2023) & (pa.revision_vintage == "2024")]["domestic_migration"].notna().all()
    )
    assert "PR" in set(out["state"]) and "US" not in set(out["state"])


def test_gazetteer_state_and_county(ctx):
    a1 = artifact_from_fixture("gazetteer_2024.zip", ctx, extra={"vintage": 2024})
    a2 = artifact_from_fixture("gazetteer_2020_counties_sample.zip", ctx, extra={"vintage": 2020})
    out = census.GazetteerConnector().parse([a1, a2], ctx)
    out = _finish(out, "geography", ctx)
    pa24 = out[(out.state == "PA") & (out.year == 2024)].iloc[0]["land_area_sq_miles"]
    pa20 = out[(out.state == "PA") & (out.year == 2020)].iloc[0]["land_area_sq_miles"]
    assert abs(pa24 - 44742) < 5 and abs(pa20 - pa24) < 5  # county sum matches state file


def test_urban_rural_parse(ctx):
    art = artifact_from_fixture(
        "ua_county_2020_sample.xlsx",
        ctx,
        as_name="2020_UA_COUNTY.xlsx",
        extra={"census_year": 2020},
    )
    out = census.UrbanRuralConnector().parse([art], ctx)
    out = _finish(out, "urban_rural", ctx)
    pa = out[out.state == "PA"].iloc[0]
    assert 0.7 < pa["pct_urban"] < 0.8 and abs(pa["pct_urban"] + pa["pct_rural"] - 1) < 1e-9
    assert pa["publication_date"] == pd.Timestamp("2022-12-31")


def test_acs_normalizer_from_format_fixture(ctx, fixtures_dir: Path):
    payload = json.load(open(fixtures_dir / "acs_format_fixture.json"))
    frame = census.parse_acs_json(payload)
    out = census.normalize_acs([frame], 2023, "acs1")
    assert set(out["state"]) == {"PA", "DE"}
    row = out[out.state == "PA"].iloc[0]
    assert (
        row["publication_date"] == pd.Timestamp("2024-09-30")
        and row["revision_vintage"] == "acs1-2023"
    )
    assert abs(row["pct_male"] + row["pct_female"] - 1) > -1  # computed without error
    edu = [
        "pct_less_than_high_school",
        "pct_high_school",
        "pct_some_college",
        "pct_associate_degree",
        "pct_bachelors",
        "pct_graduate_degree",
    ]
    assert out[edu].notna().all().all()
    assert len(census.acs_variable_list()) == len(set(census.acs_variable_list()))


def test_acs_requires_key(ctx):
    with pytest.raises(AuthenticationError):
        census.AcsProfileConnector().fetch(ctx)


# -------------------------------------------------------------------- BLS


def test_laus_bulk_parse(ctx):
    art = artifact_from_fixture("laus_flat_sample.tsv", ctx, as_name="la.data.3.AllStatesS.tsv")
    out = bls.LausConnector().parse([art], ctx)
    out = _finish(out, "labor", ctx)
    assert set(out["state"]) == {"PA", "DE"}
    pa = out[(out.state == "PA") & (out.date == "2024-08-01")].iloc[0]
    assert 0 < pa["unemployment_rate"] < 10 and pa["labor_force"] > 6_000_000
    assert pa["publication_date"] == pd.Timestamp("2024-09-21") and pa["publication_date_estimated"]
    assert pa["seasonally_adjusted"]


def test_laus_series_ids():
    sid = bls.laus_series_id("42", "03")
    assert sid == "LASST420000000000003" and len(sid) == 20
    assert bls.parse_laus_series_id(sid) == ("42", "03", True)
    assert bls.parse_laus_series_id("XYZ") is None


def test_laus_mode_requires_contact_email(ctx):
    with pytest.raises(DatasetUnavailableError):
        bls.LausConnector()._mode(
            type("C", (), {"option": lambda self, k, d=None: "bulk", "settings": ctx.settings})()
        )


def test_cpi_and_ces_parse(ctx):
    a1 = artifact_from_fixture("bls_cpi_response.json", ctx, as_name="bls_2015_2024_part0.json")
    out = bls.CpiConnector().parse([a1], ctx)
    out = _finish(out, "national_economy", ctx)
    assert set(out["measure"]) == {"cpi_all_items", "cpi_core"}
    assert out["value"].gt(100).all()
    nsa = out[(out.series_id == "CUUR0000SA0")].sort_values("date").iloc[-1]
    assert nsa["publication_date"] == pd.Timestamp(
        release_month_end(nsa["date"]) + pd.Timedelta(days=15)
    )
    a2 = artifact_from_fixture("bls_ces_response.json", ctx, as_name="bls_2015_2024_part0.json")
    out2 = bls.CesNationalConnector().parse([a2], ctx)
    out2 = _finish(out2, "national_economy", ctx)
    assert {"nonfarm_payrolls", "unemployment_rate"} <= set(out2["measure"])


def release_month_end(ts: pd.Timestamp) -> pd.Timestamp:
    return ts + pd.offsets.MonthEnd(0)


def test_qcew_parse(ctx):
    art = artifact_from_fixture(
        "qcew_2023_42_sample.csv",
        ctx,
        as_name="qcew_2023_42.csv",
        extra={"year": 2023, "state": "PA"},
    )
    out = bls.QcewConnector().parse([art], ctx)
    out = _finish(out, "industry", ctx)
    total = out[(out.industry_code == "10") & (out.own_code == "0")].iloc[0]
    assert total["annual_avg_employment"] > 5_000_000
    assert "31-33" in set(out["industry_code"]) and "1013" in set(out["industry_code"])
    assert total["publication_date"] == pd.Timestamp("2024-06-30")


# -------------------------------------------------------------------- FEC


def test_fec_candidate_master_parse(ctx):
    art = artifact_from_fixture(
        "fec_cn24_sample.zip", ctx, as_name="cn2024.zip", extra={"cycle": 2024}
    )
    out = fec.CandidateMasterConnector().parse([art], ctx)
    out = _finish(out, "candidates", ctx)
    assert (out["office"] == "senate").all() and (
        out["state"] == "PA"
    ).mean() > 0.9  # one WY filer has a PA mailing address
    assert {"I", "C"} <= set(out["incumbent_challenger_status"].dropna())
    assert (out["district"] == "statewide").all()
    assert (out["publication_date"] == pd.Timestamp("2024-06-30")).all() and out[
        "publication_date_estimated"
    ].all()


def test_fec_candidate_finance_parse(ctx):
    art = artifact_from_fixture(
        "fec_weball24_sample.zip", ctx, as_name="weball2024.zip", extra={"cycle": 2024}
    )
    out = fec.CandidateFinanceConnector().parse([art], ctx)
    out = _finish(out, "candidate_finance", ctx)
    top = out.sort_values("total_receipts", ascending=False).iloc[0]
    assert top["total_receipts"] > 1_000_000 and top["office"] == "senate"
    assert out["coverage_end_date"].notna().all()
    assert (out["publication_date"] <= pd.Timestamp(ctx.retrieval_date)).all()


def test_fec_pipe_field_count_check(tmp_path: Path):
    import zipfile

    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cn.txt", "a|b|c\n")
    with pytest.raises(SchemaChangeError):
        fec.read_pipe_zip(z, fec.CN_COLUMNS)


# ------------------------------------------------------------------- NAEP


def test_naep_parse(ctx):
    art = artifact_from_fixture(
        "naep_math_grade4_sample.json", ctx, as_name="naep_mathematics_grade4.json"
    )
    out = naep.NaepStateConnector().parse([art], ctx)
    out = _finish(out, "naep", ctx)
    pa22 = out[(out.state == "PA") & (out.assessment_year == 2022)].iloc[0]
    assert (
        200 < pa22["average_score"] < 260
        and pa22["subject"] == "mathematics"
        and pa22["grade"] == 4
    )
    assert (
        0 < pa22["pct_at_or_above_proficient"] < 1
        and pa22["pct_at_or_above_basic"] > pa22["pct_at_or_above_proficient"]
    )
    assert out[out.assessment_year == 2024]["publication_date"].iloc[0] == pd.Timestamp(
        "2025-06-30"
    )


# -------------------------------------------------------------------- BEA


def test_bea_normalizer_from_format_fixture(ctx, fixtures_dir: Path):
    payload = json.load(open(fixtures_dir / "bea_format_fixture.json"))
    df = bea.parse_bea_payload(payload)
    out = bea.normalize_bea(df, "real_gdp", "SAGDP9N", "1", bea.release_calendar.bea_annual)
    assert set(out["state"]) == {"PA", "DE"}  # national row dropped
    pa23 = out[(out.state == "PA") & (out.year == 2023)].iloc[0]
    assert pa23["value"] == 812345.0 and pa23["publication_date"] == pd.Timestamp("2024-09-30")
    with pytest.raises(AuthenticationError):
        bea.StateGdpConnector().fetch(ctx)


# ----------------------------------------------------------- manual CSVs


def _manual(ctx, fixture: str, dataset: str, source: str, name: str):  # noqa: ANN001
    manual_dir = ctx.paths.raw_dataset_dir(source, dataset) / "manual"
    manual_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(Path(__file__).parent.parent / "fixtures" / fixture, manual_dir / name)
    ctx.raw_dir = ctx.paths.raw_dir(source, dataset, ctx.retrieval_date)
    return manual_dir


def test_race_polls_manual_adapter(ctx):
    _manual(ctx, "race_polls_template.csv", "polls-races", "Polling", "race_polls.csv")
    conn = polling.RacePollsConnector()
    arts = conn.fetch(ctx)
    out = _finish(conn.parse(arts, ctx), "polls", ctx)
    assert len(out) == 3 and set(out["state"]) == {"PA", "OH"}
    assert out["dem_pct"].between(0, 1).all()  # 0-100 and 0-1 inputs both normalised
    assert out.loc[out.poll_id == "P1", "poll_margin"].iloc[0] == pytest.approx(0.02)
    assert not out["publication_date_estimated"].any()


def test_approval_and_generic_adapters(ctx):
    _manual(ctx, "approval_polls_template.csv", "polls-approval", "Polling", "approval_polls.csv")
    conn = polling.ApprovalPollsConnector()
    out = _finish(conn.parse(conn.fetch(ctx), ctx), "approval_polls", ctx)
    assert out["net_approval"].lt(0).all()
    _manual(
        ctx,
        "generic_ballot_template.csv",
        "polls-generic-ballot",
        "Polling",
        "generic_ballot_polls.csv",
    )
    conn2 = polling.GenericBallotConnector()
    out2 = _finish(conn2.parse(conn2.fetch(ctx), ctx), "generic_ballot_polls", ctx)
    assert out2["generic_margin"].gt(0).all()


def test_manual_adapter_requires_publication_date(ctx, tmp_path: Path):
    manual_dir = _manual(
        ctx, "approval_polls_template.csv", "polls-approval", "Polling", "approval_polls.csv"
    )
    df = pd.read_csv(manual_dir / "approval_polls.csv")
    df.loc[0, "publication_date"] = None
    df.to_csv(manual_dir / "approval_polls.csv", index=False)
    conn = polling.ApprovalPollsConnector()
    with pytest.raises(SchemaChangeError):
        conn.parse(conn.fetch(ctx), ctx)


def test_pew_religion_adapter(ctx):
    _manual(ctx, "religion_template.csv", "pew-religion", "Pew", "religion.csv")
    conn = pew.ReligionConnector()
    out = _finish(conn.parse(conn.fetch(ctx), ctx), "religion", ctx)
    assert set(out["state"]) == {"PA", "DE"} and out["pct_catholic"].between(0, 1).all()
    assert out["publication_date"].eq(pd.Timestamp("2015-05-12")).all()


def test_manual_missing_dir_is_clear_error(ctx):
    ctx.raw_dir = ctx.paths.raw_dir("Pew", "pew-religion", dt.date(2026, 9, 20))
    with pytest.raises(DatasetUnavailableError, match="manual"):
        pew.ReligionConnector().fetch(ctx)
