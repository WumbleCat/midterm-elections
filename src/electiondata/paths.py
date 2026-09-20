"""Filesystem layout of the local data store.

    data/
      raw/{source}/{dataset}/{retrieval_date}/   immutable downloads
      staging/{dataset}/{retrieval_date}.parquet  parsed-as-received tables
      processed/{table}/{dataset}.parquet         canonical normalized tables
      features/                                   modelling-ready feature datasets
      manifests/ingestion_runs.parquet            machine-readable run manifest
      manifests/runs/{run_id}.json                full per-run metadata
      electiondata.duckdb                         views over processed parquet
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def from_settings(cls) -> DataPaths:
        return cls(get_settings().data_dir)

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def processed(self) -> Path:
        return self.root / "processed"

    @property
    def features(self) -> Path:
        return self.root / "features"

    @property
    def manifests(self) -> Path:
        return self.root / "manifests"

    @property
    def manifest_file(self) -> Path:
        return self.manifests / "ingestion_runs.parquet"

    @property
    def run_metadata_dir(self) -> Path:
        return self.manifests / "runs"

    @property
    def duckdb_path(self) -> Path:
        return self.root / "electiondata.duckdb"

    def raw_dir(self, source: str, dataset: str, retrieval_date: dt.date | str) -> Path:
        if isinstance(retrieval_date, dt.date):
            retrieval_date = retrieval_date.isoformat()
        return self.raw / source.lower() / dataset.lower() / retrieval_date

    def raw_dataset_dir(self, source: str, dataset: str) -> Path:
        return self.raw / source.lower() / dataset.lower()

    def staging_file(self, dataset_id: str, retrieval_date: dt.date | str) -> Path:
        if isinstance(retrieval_date, dt.date):
            retrieval_date = retrieval_date.isoformat()
        return self.staging / dataset_id / f"{retrieval_date}.parquet"

    def table_dir(self, table: str) -> Path:
        return self.processed / table

    def processed_file(self, table: str, dataset_id: str) -> Path:
        return self.table_dir(table) / f"{dataset_id}.parquet"

    def ensure(self) -> None:
        for p in (
            self.raw,
            self.staging,
            self.processed,
            self.features,
            self.manifests,
            self.run_metadata_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


def get_paths() -> DataPaths:
    return DataPaths.from_settings()
