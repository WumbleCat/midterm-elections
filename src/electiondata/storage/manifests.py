"""Machine-readable ingestion manifest.

* ``data/manifests/ingestion_runs.parquet`` — one row per run (append-only, rewritten atomically)
* ``data/manifests/runs/{run_id}.json`` — full metadata (artifacts, params, validation summary)

The manifest is the source of truth for "when was this last pulled successfully"
in ``electiondata status`` and ``docs/STATUS.md``.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..paths import DataPaths, get_paths
from .parquet import read_parquet, write_parquet_atomic

MANIFEST_COLUMNS = [
    "run_id",
    "source",
    "dataset",
    "started_at",
    "completed_at",
    "status",
    "retrieval_date",
    "source_url",
    "raw_path",
    "checksum",
    "row_count",
    "schema_version",
    "parser_version",
    "normalized_table",
    "processed_path",
    "validation_errors",
    "validation_warnings",
    "error",
]


def new_run_id(dataset_id: str, started_at: dt.datetime | None = None) -> str:
    started_at = started_at or dt.datetime.now(dt.UTC)
    return f"{started_at:%Y%m%dT%H%M%S}-{dataset_id}-{uuid.uuid4().hex[:6]}"


@dataclass
class RunRecord:
    run_id: str
    source: str
    dataset: str
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    status: str = "running"  # running | success | failed | skipped
    retrieval_date: dt.date | None = None
    source_url: str | None = None
    raw_path: str | None = None
    checksum: str | None = None
    row_count: int | None = None
    schema_version: str | None = None
    parser_version: str | None = None
    normalized_table: str | None = None
    processed_path: str | None = None
    validation_errors: int | None = None
    validation_warnings: int | None = None
    error: str | None = None
    # extended metadata only written to the JSON file
    request_params: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    validation_issues: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        row = {k: getattr(self, k) for k in MANIFEST_COLUMNS}
        if row["retrieval_date"] is not None:
            row["retrieval_date"] = pd.Timestamp(row["retrieval_date"])
        return row

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=_json_default, indent=2)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


class ManifestStore:
    def __init__(self, paths: DataPaths | None = None):
        self.paths = paths or get_paths()

    def _empty(self) -> pd.DataFrame:
        return pd.DataFrame(columns=MANIFEST_COLUMNS)

    def read(self) -> pd.DataFrame:
        f = self.paths.manifest_file
        if not f.exists():
            return self._empty()
        df = read_parquet(f)
        for col in MANIFEST_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[MANIFEST_COLUMNS]

    def append(self, record: RunRecord) -> None:
        self.paths.manifests.mkdir(parents=True, exist_ok=True)
        self.paths.run_metadata_dir.mkdir(parents=True, exist_ok=True)
        existing = self.read()
        row = pd.DataFrame([record.to_row()])
        # Replace any earlier row with the same run_id (a run is written at start and at end).
        existing = existing[existing["run_id"] != record.run_id]
        combined = pd.concat([existing, row], ignore_index=True) if not existing.empty else row
        combined = _coerce(combined)
        write_parquet_atomic(combined, self.paths.manifest_file)
        (self.paths.run_metadata_dir / f"{record.run_id}.json").write_text(
            record.to_json(), encoding="utf-8"
        )

    def runs(self, dataset: str | None = None, limit: int | None = None) -> pd.DataFrame:
        df = self.read()
        if dataset:
            df = df[df["dataset"] == dataset]
        df = df.sort_values("started_at", ascending=False)
        if limit:
            df = df.head(limit)
        return df.reset_index(drop=True)

    def last_success(self, dataset: str) -> pd.Series | None:
        df = self.read()
        ok = df[(df["dataset"] == dataset) & (df["status"] == "success")]
        if ok.empty:
            return None
        return ok.sort_values("completed_at").iloc[-1]

    def last_run(self, dataset: str) -> pd.Series | None:
        df = self.read()
        sub = df[df["dataset"] == dataset]
        if sub.empty:
            return None
        return sub.sort_values("started_at").iloc[-1]

    def latest_by_dataset(self) -> pd.DataFrame:
        """Last run and last successful run per dataset (used by status reports)."""
        df = self.read()
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "dataset",
                    "last_status",
                    "last_run",
                    "last_success",
                    "last_row_count",
                    "last_error",
                ]
            )
        df = df.sort_values("started_at")
        last = df.groupby("dataset").tail(1).set_index("dataset")
        succ = df[df["status"] == "success"].groupby("dataset").tail(1).set_index("dataset")
        out = pd.DataFrame(
            {
                "last_status": last["status"],
                "last_run": last["started_at"],
                "last_error": last["error"],
                "last_success": succ["completed_at"].reindex(last.index),
                "last_row_count": succ["row_count"].reindex(last.index),
            }
        )
        return out.reset_index()

    def run_metadata(self, run_id: str) -> dict[str, Any] | None:
        f = self.paths.run_metadata_dir / f"{run_id}.json"
        if not f.exists():
            return None
        return json.loads(f.read_text(encoding="utf-8"))


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("started_at", "completed_at", "retrieval_date"):
        out[col] = pd.to_datetime(out[col], errors="coerce", utc=col != "retrieval_date")
    for col in ("row_count", "validation_errors", "validation_warnings"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in MANIFEST_COLUMNS:
        if col not in (
            "started_at",
            "completed_at",
            "retrieval_date",
            "row_count",
            "validation_errors",
            "validation_warnings",
        ):
            out[col] = out[col].astype("string")
    return out
