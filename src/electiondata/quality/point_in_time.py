"""Point-in-time filtering utilities.

A model evaluated as of date ``T`` must not see information published after
``T``. These helpers make that cut explicit and refuse to guess when a table
carries no publication dates.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, overload

import pandas as pd

from ..exceptions import PointInTimeError
from ..logging import get_logger

log = get_logger("point_in_time")

DateLike = str | dt.date | dt.datetime | pd.Timestamp


@overload
def to_date(value: None) -> None: ...


@overload
def to_date(value: DateLike) -> dt.date: ...


def to_date(value: DateLike | None) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    parsed = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(parsed):
        raise PointInTimeError(f"unparseable date: {value!r}")
    return parsed.date()


def filter_as_of(
    df: pd.DataFrame,
    as_of: DateLike | None,
    *,
    publication_col: str = "publication_date",
    fallback_cols: Sequence[str] = ("retrieval_date",),
    strict: bool = True,
    keep_unknown: bool = False,
) -> pd.DataFrame:
    """Return rows whose publication date is on or before ``as_of``.

    * ``as_of=None`` returns the frame unchanged.
    * Rows with a null publication date are dropped unless ``keep_unknown`` is
      True (they cannot be proven available).
    * If ``publication_col`` is absent, ``fallback_cols`` are tried in order and
      a warning is logged; if none exist and ``strict`` is True a
      :class:`PointInTimeError` is raised.
    """
    if as_of is None or df.empty:
        return df
    cutoff = pd.Timestamp(to_date(as_of))
    col = publication_col
    if col not in df.columns or df[col].isna().all():
        candidates = [c for c in fallback_cols if c in df.columns]
        if not candidates:
            if strict:
                raise PointInTimeError(
                    f"cannot apply as_of={cutoff.date()}: no {publication_col!r} column and no fallback"
                )
            return df
        col = candidates[0]
        log.warning(
            "point-in-time filter using fallback column",
            extra={"fallback": col, "as_of": str(cutoff.date())},
        )
    pub = pd.to_datetime(df[col], errors="coerce")
    mask = pub <= cutoff
    if keep_unknown:
        mask = mask | pub.isna()
    out = df.loc[mask].copy()
    dropped = len(df) - len(out)
    if dropped:
        log.debug(
            "point-in-time filter dropped rows",
            extra={"dropped": dropped, "as_of": str(cutoff.date())},
        )
    return out


def latest_as_of(
    df: pd.DataFrame,
    as_of: DateLike | None,
    keys: Sequence[str],
    *,
    order_col: str = "observation_date",
    publication_col: str = "publication_date",
    vintage_col: str | None = "revision_vintage",
) -> pd.DataFrame:
    """Per key, return the most recent observation available as of ``as_of``.

    Ties on ``order_col`` are broken by the latest vintage that was itself
    published by ``as_of`` — so revised values are used only once they existed.
    """
    avail = filter_as_of(df, as_of, publication_col=publication_col)
    if avail.empty:
        return avail
    sort_cols = [order_col]
    if publication_col in avail.columns:
        sort_cols.append(publication_col)
    if vintage_col and vintage_col in avail.columns:
        sort_cols.append(vintage_col)
    ordered = avail.sort_values(sort_cols, na_position="first")
    return ordered.groupby(list(keys), as_index=False, sort=False).tail(1).reset_index(drop=True)


def assert_no_future_rows(
    df: pd.DataFrame, as_of: DateLike, *, publication_col: str = "publication_date"
) -> None:
    """Raise :class:`PointInTimeError` if any row was published after ``as_of``."""
    if publication_col not in df.columns:
        raise PointInTimeError(f"column {publication_col!r} missing; cannot audit leakage")
    cutoff = pd.Timestamp(to_date(as_of))
    pub = pd.to_datetime(df[publication_col], errors="coerce")
    bad = df.loc[pub > cutoff]
    if not bad.empty:
        raise PointInTimeError(
            f"{len(bad)} rows published after as_of={cutoff.date()} (max {pub.max().date()})"
        )


def leakage_report(
    df: pd.DataFrame, as_of: DateLike, *, publication_col: str = "publication_date"
) -> dict[str, Any]:
    """Summarise how many rows would be excluded by the as_of cut (for audits)."""
    cutoff = pd.Timestamp(to_date(as_of))
    if publication_col not in df.columns:
        return {"as_of": str(cutoff.date()), "rows": len(df), "publication_column": None}
    pub = pd.to_datetime(df[publication_col], errors="coerce")
    return {
        "as_of": str(cutoff.date()),
        "rows": len(df),
        "publication_column": publication_col,
        "rows_after_as_of": int((pub > cutoff).sum()),
        "rows_unknown_publication": int(pub.isna().sum()),
        "rows_available": int((pub <= cutoff).sum()),
        "estimated_publication_rows": int(df["publication_date_estimated"].fillna(False).sum())
        if "publication_date_estimated" in df.columns
        else None,
        "max_publication_date": None if pub.dropna().empty else str(pub.max().date()),
    }
