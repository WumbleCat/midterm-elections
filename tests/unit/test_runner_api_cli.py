"""Offline end-to-end tests: runner → processed parquet → API / DuckDB / features / CLI."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from conftest import FIXTURES
from electiondata.exceptions import DatasetUnavailableError
from electiondata.ingestion import registry
from electiondata.ingestion.base import RawArtifact
from electiondata.ingestion.runner import ingest_dataset
from electiondata.ingestion.sources import bls, census, eac, fec, medsl, naep
from electiondata.storage.manifests import ManifestStore
from electiondata.storage.parquet import read_table

# ------------------------------------------------- offline connector doubles


def _copy(ctx, name: str, as_name: str, extra: dict | None = None) -> RawArtifact:  # noqa: ANN001
    """Store a fixture through the context (same immutable placement as real downloads)."""
    art = ctx.write_bytes((FIXTURES / name).read_bytes(), as_name, url=f"fixture://{name}")
    art.extra = extra or {}
    return art


class OfflineSenate(medsl.SenateResultsConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "medsl_senate_sample.csv", "1976-2024-senate.csv")]


class OfflinePresident(medsl.PresidentResultsConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "medsl_president_sample.csv", "1976-2024-president.csv")]


class OfflineEavs(eac.EavsConnector):
    def fetch(self, ctx):  # noqa: ANN001
        a = _copy(ctx, "eavs_2022_sample.zip", "eavs_2022.zip", {"year": 2022})
        a.url = eac.EAVS_FILES[2022]
        return [a]


class OfflinePep(census.PepPopulationConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [
            _copy(ctx, f"pep_vintage_{v}.csv", f"pep_vintage_{v}.csv", {"vintage": v})
            for v in (2009, 2019, 2024)
        ]


class OfflineGazetteer(census.GazetteerConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "gazetteer_2024.zip", "gazetteer_2024.zip", {"vintage": 2024})]


class OfflineUrban(census.UrbanRuralConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [
            _copy(ctx, "ua_county_2020_sample.xlsx", "2020_UA_COUNTY.xlsx", {"census_year": 2020})
        ]


class OfflineLaus(bls.LausConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "laus_flat_sample.tsv", "la.data.3.AllStatesS.tsv")]


class OfflineCpi(bls.CpiConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "bls_cpi_response.json", "bls_2015_2024_part0.json")]


class OfflineCes(bls.CesNationalConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "bls_ces_response.json", "bls_2015_2024_part0.json")]


class OfflineQcew(bls.QcewConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [
            _copy(ctx, "qcew_2023_42_sample.csv", "qcew_2023_42.csv", {"year": 2023, "state": "PA"})
        ]


class OfflineCn(fec.CandidateMasterConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "fec_cn24_sample.zip", "cn2024.zip", {"cycle": 2024})]


class OfflineWeball(fec.CandidateFinanceConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "fec_weball24_sample.zip", "weball2024.zip", {"cycle": 2024})]


class OfflineNaep(naep.NaepStateConnector):
    def fetch(self, ctx):  # noqa: ANN001
        return [_copy(ctx, "naep_math_grade4_sample.json", "naep_mathematics_grade4.json")]


OFFLINE = {
    "medsl-senate": OfflineSenate,
    "medsl-president": OfflinePresident,
    "eac-eavs": OfflineEavs,
    "census-pep-population": OfflinePep,
    "census-gazetteer": OfflineGazetteer,
    "census-urban-rural": OfflineUrban,
    "bls-laus": OfflineLaus,
    "bls-cpi": OfflineCpi,
    "bls-ces-national": OfflineCes,
    "bls-qcew": OfflineQcew,
    "fec-candidate-master": OfflineCn,
    "fec-candidate-finance": OfflineWeball,
    "naep-state": OfflineNaep,
}


@pytest.fixture
def offline_registry(monkeypatch: pytest.MonkeyPatch):
    def load(self):  # noqa: ANN001
        return OFFLINE[self.id]()

    monkeypatch.setattr(registry.SourceSpec, "load_connector", load)


@pytest.fixture
def store(data_dir: Path, offline_registry):  # noqa: ANN001
    """A populated temporary data store built through the real runner."""
    for did in OFFLINE:
        res = ingest_dataset(did)
        assert res.ok, f"{did}: {res.error}"
    return data_dir


# ------------------------------------------------------------------ runner


def test_runner_end_to_end_and_idempotent(data_dir: Path, offline_registry):
    r1 = ingest_dataset("medsl-senate")
    assert r1.ok and r1.rows > 0 and r1.processed_path.exists()
    assert r1.raw_dir.exists() and any(r1.raw_dir.iterdir())
    manifest = ManifestStore()
    row = manifest.last_success("medsl-senate")
    assert row["checksum"] and int(row["row_count"]) == r1.rows and row["status"] == "success"
    meta = manifest.run_metadata(r1.run_id)
    assert meta["artifacts"][0]["sha256"] == r1.artifacts[0].sha256
    assert meta["normalized_table"] == "election_results" and meta["parser_version"]
    # staging copy written
    assert list((data_dir / "staging" / "medsl-senate").glob("*.parquet"))
    # second run: identical raw artifact reused, processed rows unchanged, no duplicate rows
    r2 = ingest_dataset("medsl-senate")
    assert r2.ok and r2.artifacts[0].reused and r2.rows == r1.rows
    table = read_table("election_results")
    key = ["state", "year", "office", "district", "candidate", "party_raw", "special"]
    assert not table.duplicated(subset=key).any()
    assert len(manifest.runs(dataset="medsl-senate")) == 2
    # provenance present on every row
    for col in ("source", "dataset_id", "retrieval_date", "publication_date", "ingestion_run_id"):
        assert table[col].notna().all()


def test_runner_records_failures(data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    class Broken(medsl.SenateResultsConnector):
        def fetch(self, ctx):  # noqa: ANN001
            raise DatasetUnavailableError("upstream gone")

    monkeypatch.setattr(registry.SourceSpec, "load_connector", lambda self: Broken())
    res = ingest_dataset("medsl-senate")
    assert res.status == "failed" and "upstream gone" in res.error
    row = ManifestStore().last_run("medsl-senate")
    assert row["status"] == "failed" and "DatasetUnavailableError" in row["error"]
    assert not (data_dir / "processed" / "election_results").exists()


def test_runner_blocked_without_key(data_dir: Path):
    res = ingest_dataset("census-acs-profile")
    assert res.status == "failed" and "CENSUS_API_KEY" in res.error


def test_runner_from_raw(data_dir: Path, offline_registry):
    ingest_dataset("medsl-senate")
    res = ingest_dataset("medsl-senate", from_raw="latest")
    assert res.ok and res.notes and "re-parsing" in res.notes[0]


def test_runner_validation_failure_blocks_write(data_dir: Path, monkeypatch: pytest.MonkeyPatch):
    class Bad(medsl.SenateResultsConnector):
        def fetch(self, ctx):  # noqa: ANN001
            return [_copy(ctx, "medsl_senate_sample.csv", "1976-2024-senate.csv")]

        def parse(self, artifacts, ctx):  # noqa: ANN001
            out = super().parse(artifacts, ctx)
            out.loc[out.index[0], "votes"] = -1  # negative vote count -> validation error
            return out

    monkeypatch.setattr(registry.SourceSpec, "load_connector", lambda self: Bad())
    res = ingest_dataset("medsl-senate")
    assert res.status == "failed" and "validation" in res.error
    assert res.validation is not None and any(
        i.rule == "negative_count" for i in res.validation.errors
    )
    res2 = ingest_dataset("medsl-senate", fail_on_validation_error=False)
    assert res2.ok


# --------------------------------------------------------------------- api


def test_api_queries(store: Path):
    import electiondata as ed

    r = ed.elections.results(year=2024, office="senate", state="PA")
    assert len(r) == 1 and r.iloc[0]["winner_party"] == "REP"
    c = ed.elections.results(year=2024, office="senate", state="pa", level="candidate")
    assert set(c["party"]) >= {"DEM", "REP"}
    assert ed.elections.results(year=2024, office="senate", state="PA", as_of="2024-10-01").empty
    assert (
        ed.elections.results(year=[2020, 2024], office="president", state=["PA", "GA"]).shape[0]
        == 4
    )
    t = ed.elections.turnout(state="PA")
    assert t.iloc[0]["turnout_registered"] == pytest.approx(5410022 / 8873144)
    lab = ed.economics.labor(state="PA", as_of="2024-10-01")
    assert pd.to_datetime(lab["date"]).max() == pd.Timestamp("2024-08-01")
    snap = ed.economics.labor_snapshot("2024-10-15", state="PA").iloc[0]
    assert snap["labor_month"] == pd.Timestamp("2024-08-01")
    pop = ed.demographics.population(state="PA", year=2023)
    assert len(pop) == 1 and pop.iloc[0]["revision_vintage"] == "2024"
    assert len(ed.demographics.population(state="PA", year=2023, latest_vintage_only=False)) == 1
    assert ed.demographics.population(state="PA", as_of="2024-06-01", year=2023).empty
    fin = ed.candidates.finance(state="PA", year=2024, office="senate")
    assert fin.iloc[0]["total_receipts"] >= fin.iloc[-1]["total_receipts"]
    inc = ed.candidates.incumbency(2024, "senate")
    assert inc.set_index("state").loc["PA", "dem_incumbent"]
    with pytest.raises(DatasetUnavailableError):
        ed.polls.races()
    with pytest.raises(ValueError):
        ed.elections.results(office="mayor")
    assert not ed.sources().empty and not ed.runs().empty
    hist = ed.elections.history("senate", state="PA")
    assert hist[hist.year == 2024].iloc[0]["prev_election_year"] == 2018


def test_duckdb_views_and_queries(store: Path):
    import electiondata as ed
    from electiondata.storage.duckdb import list_views, query_table, rebuild_database

    views = rebuild_database()
    assert {"election_results", "labor", "turnout", "ingestion_runs"} <= set(views)
    assert set(list_views()) >= set(views)
    df = ed.query(
        "SELECT state, count(*) AS n FROM election_results WHERE year = 2024 GROUP BY 1 ORDER BY 1"
    )
    assert "PA" in set(df["state"])
    sub = query_table(
        "labor",
        {"state": "PA", "seasonally_adjusted": True},
        columns=["date", "unemployment_rate"],
        order_by=["date"],
    )
    assert list(sub.columns) == ["date", "unemployment_rate"] and len(sub) > 12
    assert query_table("labor", {"state": ["PA", "DE"]})["state"].nunique() == 2
    with pytest.raises(DatasetUnavailableError):
        query_table("polls")


def test_feature_build_is_point_in_time(store: Path):
    import electiondata as ed
    from electiondata.transform.features import audit_features

    fb = ed.features.build(
        year=2024, office="senate", as_of="2024-10-15", state=["PA"], return_build=True
    )
    row = fb.frame.iloc[0]
    assert row["state"] == "PA" and row["as_of"] == pd.Timestamp("2024-10-15")
    assert row["dem_two_party_share"] == pytest.approx(
        3384180 / (3384180 + 3399295)
    )  # target attached
    assert row["prev_election_year"] == 2018 and row["lean_year"] == 2020
    assert row["labor_month"] == pd.Timestamp("2024-08-01")
    assert (
        row["population_year"] == 2023
        and row["population_vintage"] == "2019"
        or row["population_vintage"] in ("2019", "2023")
    )
    assert "finance" in fb.families_unavailable  # only a 2026 snapshot exists
    assert row["dem_incumbent"] and not row["open_seat"]
    assert row["naep_math_grade4"] > 200
    assert fb.path is not None and fb.path.exists() and fb.path.with_suffix(".json").exists()
    audit = audit_features(fb)
    assert audit["forecast_before_election"] and not audit["post_as_of_families"]
    for fam, info in fb.metadata["families"].items():
        if fam != "targets" and info.get("available"):
            assert info["max_publication_date"] <= "2024-10-15", fam
    # a later as_of sees more data (September labour month)
    later = ed.features.build(
        year=2024, office="senate", as_of="2024-11-04", state=["PA"], write=False
    )
    assert later.iloc[0]["labor_month"] == pd.Timestamp("2024-09-01")
    # audit helper via API
    assert ed.features.audit(2024, "senate", "2024-10-15")["as_of"] == "2024-10-15"


# --------------------------------------------------------------------- cli


def test_cli_smoke(store: Path):
    from electiondata.cli import app

    runner = CliRunner()
    r = runner.invoke(app, ["sources"])
    assert r.exit_code == 0 and "medsl-senate" in r.output and "DONE=" in r.output
    r = runner.invoke(app, ["sources", "--phase", "core", "--status", "done"])
    assert r.exit_code == 0 and "bls-laus" not in r.output
    r = runner.invoke(app, ["info", "bls-laus"])
    assert r.exit_code == 0 and "connector" in r.output
    r = runner.invoke(app, ["status"])
    assert r.exit_code == 0 and "medsl-senate" in r.output
    r = runner.invoke(app, ["status", "--markdown"])
    assert r.exit_code == 0 and "| Phase |" in r.output
    r = runner.invoke(app, ["runs", "--limit", "3"])
    assert r.exit_code == 0 and "success" in r.output
    r = runner.invoke(app, ["validate"])
    assert r.exit_code == 0 and "validation:" in r.output
    r = runner.invoke(app, ["transform"])
    assert r.exit_code == 0 and "election_race_summary" in r.output
    r = runner.invoke(app, ["rebuild-db"])
    assert r.exit_code == 0 and "views" in r.output
    r = runner.invoke(app, ["query", "SELECT count(*) AS n FROM election_race_summary"])
    assert r.exit_code == 0
    r = runner.invoke(
        app,
        [
            "build-features",
            "--year",
            "2024",
            "--office",
            "senate",
            "--as-of",
            "2024-10-15",
            "--state",
            "PA",
            "--no-write",
        ],
    )
    assert r.exit_code == 0 and "available families" in r.output
    r = runner.invoke(app, ["audit-features", "2024", "senate", "2024-10-15"])
    assert r.exit_code == 0 and "post_as_of_families" in r.output
    r = runner.invoke(app, ["ingest", "medsl-senate", "--from-raw", "latest"])
    assert r.exit_code == 0 and "success" in r.output
    r = runner.invoke(app, ["ingest", "census-acs-profile"])
    assert r.exit_code == 1 and "CENSUS_API_KEY" in r.output
    r = runner.invoke(app, ["ingest"])
    assert r.exit_code != 0
    r = runner.invoke(app, ["audit", "turnout"])
    assert r.exit_code == 0 and '"rows"' in r.output


def test_cli_docs_generation(store: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from electiondata import docs_gen
    from electiondata.cli import app

    monkeypatch.setattr(docs_gen, "docs_dir", lambda: tmp_path / "docs")
    r = CliRunner().invoke(app, ["docs"])
    assert r.exit_code == 0
    status = (tmp_path / "docs" / "STATUS.md").read_text(encoding="utf-8")
    assert "BEGIN GENERATED:status" in status and "medsl-senate" in status and "DONE:" in status
    model = (tmp_path / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")
    assert "### `election_results`" in model
    # hand-written text outside markers survives regeneration
    (tmp_path / "docs" / "STATUS.md").write_text("intro\n\n" + status, encoding="utf-8")
    docs_gen.write_generated_docs(which=("status",))
    assert (tmp_path / "docs" / "STATUS.md").read_text(encoding="utf-8").startswith("intro")
    assert docs_gen.known_broken() == []


def test_settings_and_paths_isolated(data_dir: Path):
    from electiondata.config import get_settings

    s = get_settings()
    assert (
        s.data_dir == data_dir and not s.has_key("CENSUS_API_KEY") and s.fec_api_key == "DEMO_KEY"
    )
    assert s.user_agent.startswith("electiondata/")
    assert dt.date.today() >= dt.date(2026, 1, 1)
