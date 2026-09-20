"""Live endpoint checks. Run with ``pytest --run-integration tests/integration``.

They download real (small) artifacts into a temporary data directory through
the real runner and assert on schema + a few well-known values.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from electiondata.ingestion.runner import ingest_dataset
from electiondata.storage.parquet import read_table

pytestmark = pytest.mark.integration


@pytest.fixture
def live_dir(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # bulk BLS downloads need an identifying User-Agent
    monkeypatch.setenv(
        "ELECTIONDATA_CONTACT_EMAIL",
        os.environ.get("ELECTIONDATA_CONTACT_EMAIL") or "integration-tests@example.org",
    )
    from electiondata.config import reset_settings

    reset_settings()
    return data_dir


def test_medsl_senate_live(live_dir: Path):
    res = ingest_dataset("medsl-senate")
    assert res.ok, res.error
    df = read_table("election_results")
    pa = df[(df.state == "PA") & (df.year == 2024) & (df.party == "REP")]
    assert not pa.empty and pa["votes"].max() > 3_000_000
    assert res.artifacts[0].sha256 and res.raw_dir.exists()


def test_medsl_president_live(live_dir: Path):
    res = ingest_dataset("medsl-president")
    assert res.ok, res.error
    df = read_table("election_results")
    assert df[(df.year == 2020) & (df.office == "president")]["state"].nunique() == 51


def test_eavs_live(live_dir: Path):
    res = ingest_dataset("eac-eavs", options={"years": "2022"})
    assert res.ok, res.error
    df = read_table("turnout")
    pa = df[(df.state == "PA") & (df.year == 2022)].iloc[0]
    assert 5_000_000 < pa["ballots_cast"] < 6_000_000


def test_pep_live(live_dir: Path):
    res = ingest_dataset("census-pep-population")
    assert res.ok, res.error
    df = read_table("population")
    assert (
        df[(df.state == "PA") & (df.year == 2023)]["population"]
        .between(12_500_000, 13_500_000)
        .all()
    )
    assert df["revision_vintage"].nunique() >= 3


def test_gazetteer_and_urban_rural_live(live_dir: Path):
    assert ingest_dataset("census-gazetteer", options={"vintages": "2024"}).ok
    assert ingest_dataset("census-urban-rural").ok
    geo = read_table("geography")
    assert abs(geo[geo.state == "PA"]["land_area_sq_miles"].iloc[0] - 44742) < 5
    ur = read_table("urban_rural")
    assert 0.7 < ur[ur.state == "PA"]["pct_urban"].iloc[0] < 0.8


def test_bls_laus_bulk_live(live_dir: Path):
    res = ingest_dataset("bls-laus", options={"start_year": "2023"})
    assert res.ok, res.error
    df = read_table("labor")
    assert df["state"].nunique() == 51 and pd.to_datetime(df["date"]).min().year == 2023


@pytest.mark.skipif(
    not os.environ.get("BLS_API_KEY") and os.environ.get("CI"),
    reason="keyless BLS API quota is 25 queries/day",
)
def test_bls_cpi_api_live(live_dir: Path):
    res = ingest_dataset("bls-cpi", options={"start_year": "2023"})
    assert res.ok, res.error
    df = read_table("national_economy")
    assert {"cpi_all_items", "cpi_core"} <= set(df["measure"])


def test_qcew_live(live_dir: Path):
    res = ingest_dataset("bls-qcew", options={"years": "2023"})
    assert res.ok, res.error
    df = read_table("industry")
    assert df["state"].nunique() == 51


def test_fec_bulk_live(live_dir: Path):
    assert ingest_dataset("fec-candidate-master", options={"cycles": "2024"}).ok
    assert ingest_dataset("fec-candidate-finance", options={"cycles": "2024"}).ok
    cands = read_table("candidates")
    assert (
        cands[
            (cands.state == "PA")
            & (cands.office == "senate")
            & (cands.incumbent_challenger_status == "I")
        ].shape[0]
        >= 1
    )


def test_naep_live(live_dir: Path):
    res = ingest_dataset("naep-state", options={"years": "2022"})
    assert res.ok, res.error
    df = read_table("naep")
    assert df["state"].nunique() == 51 and set(df["subject"]) == {"mathematics", "reading"}


@pytest.mark.skipif(not os.environ.get("CENSUS_API_KEY"), reason="needs CENSUS_API_KEY")
def test_acs_live(live_dir: Path):
    res = ingest_dataset("census-acs-profile", options={"years": "2023"})
    assert res.ok, res.error
    df = read_table("demographics")
    pa = df[df.state == "PA"].iloc[0]
    assert 0.2 < pa["pct_bachelors_or_higher"] < 0.5 and 35 < pa["median_age"] < 50


@pytest.mark.skipif(not os.environ.get("BEA_API_KEY"), reason="needs BEA_API_KEY")
def test_bea_live(live_dir: Path):
    for did in ("bea-state-gdp", "bea-personal-income", "bea-rpp"):
        res = ingest_dataset(did)
        assert res.ok, res.error
    df = read_table("state_economy")
    assert {"real_gdp", "personal_income", "regional_price_parity"} <= set(df["measure"])
