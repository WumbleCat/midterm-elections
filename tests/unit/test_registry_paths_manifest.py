import datetime as dt
from pathlib import Path

import pytest

from electiondata.exceptions import UnknownSourceError
from electiondata.ingestion.base import Connector, RawArtifact, _place_immutably
from electiondata.ingestion.registry import (
    REGISTRY,
    Phase,
    Status,
    get_spec,
    list_specs,
    status_counts,
)
from electiondata.paths import DataPaths, get_paths
from electiondata.storage.manifests import ManifestStore, RunRecord, new_run_id


def test_registry_integrity():
    assert len(REGISTRY) >= 25
    ids = set()
    for spec in REGISTRY.values():
        assert spec.id not in ids
        ids.add(spec.id)
        assert spec.phase in Phase
        assert spec.status in Status
        assert spec.authoritative_url.startswith("http")
        assert spec.normalized_table
        if spec.status in {Status.DONE, Status.PARTIAL, Status.BLOCKED, Status.MANUAL}:
            assert spec.connector, spec.id
            conn = spec.load_connector()
            assert isinstance(conn, Connector)
            assert conn.dataset_id == spec.id
        if spec.status == Status.DONE:
            assert spec.tested, f"{spec.id} is DONE but untested"


def test_registry_lookup_and_filters():
    assert get_spec("medsl-senate").source == "MEDSL"
    with pytest.raises(UnknownSourceError):
        get_spec("nope")
    assert all(s.phase == Phase.CORE for s in list_specs(phase="core"))
    assert all(s.phase == Phase.ECONOMICS for s in list_specs(phase=3))
    assert all(s.status == Status.DONE for s in list_specs(status="done"))
    assert all(s.source == "BLS" for s in list_specs(source="bls"))
    counts = status_counts()
    assert sum(counts.values()) == len(REGISTRY)


def test_raw_path_generation(data_dir: Path):
    paths = get_paths()
    assert paths.root == data_dir
    p = paths.raw_dir("BLS", "bls-laus", dt.date(2026, 9, 20))
    assert p == data_dir / "raw" / "bls" / "bls-laus" / "2026-09-20"
    assert paths.raw_dir("Census", "census-acs-profile", "2026-01-02").name == "2026-01-02"
    assert (
        paths.processed_file("labor", "bls-laus")
        == data_dir / "processed" / "labor" / "bls-laus.parquet"
    )
    assert paths.staging_file("bls-laus", dt.date(2026, 9, 20)).suffix == ".parquet"
    paths.ensure()
    assert (data_dir / "manifests" / "runs").is_dir()


def test_immutable_placement(tmp_path: Path):
    import hashlib

    dest = tmp_path / "file.csv"
    staging = tmp_path / "file.csv.download"
    staging.write_bytes(b"abc")
    final, reused = _place_immutably(staging, dest, hashlib.sha256(b"abc").hexdigest())
    assert final == dest and not reused
    # identical content -> reused, no new file
    staging.write_bytes(b"abc")
    final, reused = _place_immutably(staging, dest, hashlib.sha256(b"abc").hexdigest())
    assert final == dest and reused and not staging.exists()
    # different content -> new file, original untouched
    staging.write_bytes(b"xyz")
    final, reused = _place_immutably(staging, dest, hashlib.sha256(b"xyz").hexdigest())
    assert final != dest and dest.read_bytes() == b"abc" and final.read_bytes() == b"xyz"


def test_manifest_roundtrip(data_dir: Path):
    store = ManifestStore(DataPaths(data_dir))
    run_id = new_run_id("medsl-senate")
    rec = RunRecord(
        run_id=run_id,
        source="MEDSL",
        dataset="medsl-senate",
        started_at=dt.datetime.now(dt.UTC),
        retrieval_date=dt.date(2026, 9, 20),
    )
    store.append(rec)
    assert store.last_success("medsl-senate") is None
    rec.status = "success"
    rec.row_count = 42
    rec.completed_at = dt.datetime.now(dt.UTC)
    rec.artifacts = [
        RawArtifact(
            path=Path("x"), url="u", sha256="s", size_bytes=1, params={"api_key": "SECRET"}
        ).to_dict()
    ]
    store.append(rec)
    df = store.read()
    assert len(df) == 1  # same run id replaced, not duplicated
    last = store.last_success("medsl-senate")
    assert int(last["row_count"]) == 42
    meta = store.run_metadata(run_id)
    assert meta["artifacts"][0]["params"]["api_key"] == "***"
    latest = store.latest_by_dataset()
    assert latest.loc[0, "dataset"] == "medsl-senate" and latest.loc[0, "last_status"] == "success"
    assert store.runs(limit=1).shape[0] == 1
