"""Shared helpers for the public API modules."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..geo import normalize_state
from ..quality.point_in_time import DateLike, filter_as_of
from ..storage.parquet import read_table

_OFFICE_ALIASES = {
    "president": "president",
    "presidential": "president",
    "pres": "president",
    "senate": "senate",
    "us senate": "senate",
    "sen": "senate",
    "house": "house",
    "us house": "house",
    "rep": "house",
}


def norm_office(office: str | None) -> str | None:
    if office is None:
        return None
    key = office.strip().lower()
    if key not in _OFFICE_ALIASES:
        raise ValueError(f"unknown office {office!r}; use president, senate or house")
    return _OFFICE_ALIASES[key]


def require_office(office: str) -> str:
    out = norm_office(office)
    if out is None:
        raise ValueError("office is required")
    return out


def norm_states(state: str | Sequence[str] | None) -> list[str] | None:
    if state is None:
        return None
    values = [state] if isinstance(state, str) else list(state)
    out = []
    for v in values:
        s = normalize_state(v, allow_national=True)
        if s is None:
            raise ValueError(f"unknown state {v!r}")
        out.append(s)
    return out


def load(table: str) -> pd.DataFrame:
    """Read a processed table (raises DatasetUnavailableError when nothing is ingested)."""
    return read_table(table)


def apply_filters(df: pd.DataFrame, **filters: object) -> pd.DataFrame:
    out = df
    for col, value in filters.items():
        if value is None or col not in out.columns:
            continue
        if isinstance(value, list | tuple | set):
            out = out[out[col].isin(list(value))]
        else:
            out = out[out[col] == value]
    return out


def as_of_filter(df: pd.DataFrame, as_of: DateLike | None) -> pd.DataFrame:
    return filter_as_of(df, as_of) if as_of is not None else df


def latest_vintage(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Keep the newest retrieval/vintage per key (for snapshot-style tables)."""
    if df.empty:
        return df
    sort_cols = [c for c in ("retrieval_date", "revision_vintage") if c in df.columns]
    return df.sort_values(sort_cols).groupby(keys, as_index=False).tail(1)
