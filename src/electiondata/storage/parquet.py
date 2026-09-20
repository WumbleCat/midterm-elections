"""Parquet is the durable format for processed tables.

Layout: ``data/processed/{table}/{dataset_id}.parquet``. Each dataset owns one
file so a re-ingestion replaces exactly its own rows (atomic rename) and the
table is the union of all files. DuckDB views read the whole directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..exceptions import DatasetUnavailableError, StorageError
from ..paths import DataPaths, get_paths
from ..quality.schemas import SCHEMAS, enforce_schema


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise StorageError(f"failed to write {path}: {exc}") from exc
    return path


def read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pq.read_table(path).to_pandas()
    except Exception as exc:  # noqa: BLE001
        raise StorageError(f"failed to read {path}: {exc}") from exc


def write_processed(df: pd.DataFrame, table: str, dataset_id: str, paths: DataPaths | None = None) -> Path:
    paths = paths or get_paths()
    schema = SCHEMAS[table]
    df = enforce_schema(df, schema)
    return write_parquet_atomic(df, paths.processed_file(table, dataset_id))


def list_processed_files(table: str, paths: DataPaths | None = None) -> list[Path]:
    paths = paths or get_paths()
    d = paths.table_dir(table)
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.parquet") if not p.name.endswith(".tmp"))


def read_table(table: str, paths: DataPaths | None = None, *, missing_ok: bool = False) -> pd.DataFrame:
    """Read the union of all dataset files of a processed table.

    Raises :class:`DatasetUnavailableError` when nothing has been ingested
    unless ``missing_ok`` (then an empty schema-typed frame is returned).
    """
    paths = paths or get_paths()
    files = list_processed_files(table, paths)
    schema = SCHEMAS.get(table)
    if not files:
        if missing_ok:
            if schema is None:
                return pd.DataFrame()
            return enforce_schema(pd.DataFrame(columns=schema.column_names), schema, strict=False)
        raise DatasetUnavailableError(
            f"table {table!r} has no processed data yet; run `electiondata ingest ...` first"
        )
    frames = [read_parquet(f) for f in files]
    out = pd.concat(frames, ignore_index=True, sort=False)
    if schema is not None:
        out = enforce_schema(out, schema, strict=False)
    return out


def table_inventory(paths: DataPaths | None = None) -> pd.DataFrame:
    """One row per processed parquet file with its row count and modification time."""
    paths = paths or get_paths()
    rows = []
    if paths.processed.exists():
        for table_dir in sorted(p for p in paths.processed.iterdir() if p.is_dir()):
            for f in sorted(table_dir.glob("*.parquet")):
                meta = pq.read_metadata(f)
                rows.append(
                    {
                        "table": table_dir.name,
                        "dataset_id": f.stem,
                        "rows": meta.num_rows,
                        "columns": meta.num_columns,
                        "size_bytes": f.stat().st_size,
                        "modified": pd.Timestamp(f.stat().st_mtime, unit="s").floor("s"),
                        "path": str(f),
                    }
                )
    return pd.DataFrame(rows, columns=["table", "dataset_id", "rows", "columns", "size_bytes", "modified", "path"])
