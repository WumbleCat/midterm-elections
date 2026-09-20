"""Shared pytest fixtures: isolated data directory, offline ingest context, fixture paths."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration", action="store_true", default=False, help="run live integration tests"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="needs --run-integration (live network)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the package at a temporary data directory with no API keys."""
    d = tmp_path / "data"
    monkeypatch.setenv("ELECTIONDATA_DATA_DIR", str(d))
    # empty strings win over a developer's .env (load_dotenv never overrides existing vars)
    for key in (
        "CENSUS_API_KEY",
        "BLS_API_KEY",
        "BEA_API_KEY",
        "FEC_API_KEY",
        "ELECTIONDATA_CONTACT_EMAIL",
    ):
        monkeypatch.setenv(key, "")
    from electiondata.config import reset_settings

    reset_settings()
    yield d
    reset_settings()


class OfflineHttp:
    """Stand-in HttpClient that fails on any network use."""

    def __getattr__(self, name: str):  # noqa: ANN204
        def _fail(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError(f"network access attempted: {name}{args[:1]}")

        return _fail

    def close(self) -> None:
        return None


@pytest.fixture
def ctx(data_dir: Path):
    """An IngestContext with an offline HTTP client and a raw dir under the temp data dir."""
    from electiondata.config import get_settings
    from electiondata.ingestion.base import IngestContext
    from electiondata.paths import DataPaths

    paths = DataPaths(data_dir)
    paths.ensure()
    raw_dir = paths.raw_dir("test", "test-dataset", dt.date(2026, 9, 20))
    raw_dir.mkdir(parents=True, exist_ok=True)
    return IngestContext(
        settings=get_settings(),
        paths=paths,
        http=OfflineHttp(),  # type: ignore[arg-type]
        run_id="test-run",
        retrieval_date=dt.date(2026, 9, 20),
        raw_dir=raw_dir,
    )


def artifact_from_fixture(name: str, ctx, *, as_name: str | None = None, extra: dict | None = None):  # noqa: ANN001
    """Copy a fixture into the context raw dir and wrap it as a RawArtifact."""
    from electiondata.http import sha256_of_file
    from electiondata.ingestion.base import RawArtifact

    src = FIXTURES / name
    dst = ctx.raw_dir / (as_name or name)
    shutil.copy(src, dst)
    return RawArtifact(
        path=dst,
        url=f"fixture://{name}",
        sha256=sha256_of_file(dst),
        size_bytes=dst.stat().st_size,
        extra=extra or {},
    )
