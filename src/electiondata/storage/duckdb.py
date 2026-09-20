"""DuckDB analytical layer.

The DuckDB file contains *views* over the processed Parquet directories (plus
the ingestion manifest), so it can be rebuilt at any time with
:func:`rebuild_database` and is never the only copy of the data.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ..exceptions import DatasetUnavailableError, StorageError
from ..logging import get_logger
from ..paths import DataPaths, get_paths
from ..quality.schemas import SCHEMAS
from .parquet import list_processed_files

log = get_logger("duckdb")


def _sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


@contextmanager
def connect(
    paths: DataPaths | None = None, *, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    paths = paths or get_paths()
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        con = duckdb.connect(str(paths.duckdb_path), read_only=read_only)
    except duckdb.Error as exc:
        raise StorageError(f"cannot open DuckDB at {paths.duckdb_path}: {exc}") from exc
    try:
        yield con
    finally:
        con.close()


def rebuild_database(paths: DataPaths | None = None) -> list[str]:
    """(Re)create one view per processed table and for the manifest. Returns view names."""
    paths = paths or get_paths()
    created: list[str] = []
    with connect(paths) as con:
        for table in SCHEMAS:
            files = list_processed_files(table, paths)
            if not files:
                con.execute(f'DROP VIEW IF EXISTS "{table}"')
                continue
            glob = _sql_path(paths.table_dir(table) / "*.parquet")
            con.execute(
                f"CREATE OR REPLACE VIEW \"{table}\" AS SELECT * FROM read_parquet('{glob}', union_by_name=true)"
            )
            created.append(table)
        if paths.manifest_file.exists():
            con.execute(
                f"CREATE OR REPLACE VIEW ingestion_runs AS SELECT * FROM read_parquet('{_sql_path(paths.manifest_file)}')"
            )
            created.append("ingestion_runs")
    log.info("duckdb rebuilt", extra={"views": len(created), "path": str(paths.duckdb_path)})
    return created


def query(
    sql: str,
    params: Sequence[Any] | Mapping[str, Any] | None = None,
    paths: DataPaths | None = None,
) -> pd.DataFrame:
    """Run an ad-hoc SQL query against the views (rebuilding them if stale)."""
    paths = paths or get_paths()
    if not paths.duckdb_path.exists():
        rebuild_database(paths)
    with connect(paths, read_only=True) as con:
        try:
            rel = con.execute(sql, params) if params is not None else con.execute(sql)
            return rel.df()
        except duckdb.CatalogException as exc:
            raise DatasetUnavailableError(str(exc)) from exc
        except duckdb.Error as exc:
            raise StorageError(f"query failed: {exc}") from exc


def query_table(
    table: str,
    filters: Mapping[str, Any] | None = None,
    *,
    columns: Sequence[str] | None = None,
    order_by: Sequence[str] | None = None,
    paths: DataPaths | None = None,
) -> pd.DataFrame:
    """Read ``table`` directly from Parquet with simple equality/IN filters.

    Reads the Parquet directory rather than the DuckDB file so the result is
    always current even if the views have not been rebuilt.
    """
    paths = paths or get_paths()
    files = list_processed_files(table, paths)
    if not files:
        raise DatasetUnavailableError(
            f"table {table!r} has no processed data yet; run `electiondata ingest ...` first"
        )
    glob = _sql_path(paths.table_dir(table) / "*.parquet")
    cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
    where: list[str] = []
    params: list[Any] = []
    for key, value in (filters or {}).items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set):
            values = list(value)
            if not values:
                where.append("FALSE")
                continue
            where.append(f'"{key}" IN ({", ".join("?" for _ in values)})')
            params.extend(values)
        else:
            where.append(f'"{key}" = ?')
            params.append(value)
    sql = f"SELECT {cols} FROM read_parquet('{glob}', union_by_name=true)"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if order_by:
        sql += " ORDER BY " + ", ".join(f'"{c}"' for c in order_by)
    try:
        con = duckdb.connect()
        try:
            return con.execute(sql, params).df()
        finally:
            con.close()
    except duckdb.Error as exc:
        raise StorageError(f"query on {table} failed: {exc}") from exc


def list_views(paths: DataPaths | None = None) -> list[str]:
    paths = paths or get_paths()
    if not paths.duckdb_path.exists():
        return []
    with connect(paths, read_only=True) as con:
        rows = con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]
