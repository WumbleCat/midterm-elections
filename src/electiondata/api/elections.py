"""``ed.elections`` — election results, race summaries, turnout and political history."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..quality.point_in_time import DateLike
from ..transform import elections as elec_t
from ..transform import turnout as turnout_t
from ._common import apply_filters, as_of_filter, load, norm_office, norm_states, require_office


def results(
    year: int | Sequence[int] | None = None,
    office: str | None = None,
    state: str | Sequence[str] | None = None,
    district: str | None = None,
    *,
    level: str = "race",
    include_special: bool = False,
    as_of: DateLike | None = None,
) -> pd.DataFrame:
    """General-election results.

    ``level="race"`` (default) returns one row per race with Democratic/Republican
    totals, shares, two-party share, margin and winner; ``level="candidate"``
    returns the candidate-level rows as ingested.
    """
    df = load("election_results")
    df = as_of_filter(df, as_of)
    df = apply_filters(
        df,
        year=list(year) if isinstance(year, list | tuple | set) else year,
        office=norm_office(office),
        state=norm_states(state),
        district=district,
    )
    if not include_special:
        df = df[~df["special"].fillna(False)]
    if level == "candidate":
        return df.reset_index(drop=True)
    if level != "race":
        raise ValueError("level must be 'race' or 'candidate'")
    if df.empty:
        return df
    return elec_t.race_summary(df).reset_index(drop=True)


def turnout(
    year: int | Sequence[int] | None = None,
    state: str | Sequence[str] | None = None,
    *,
    as_of: DateLike | None = None,
    with_metrics: bool = True,
) -> pd.DataFrame:
    """State-level registration, ballots cast and derived turnout rates (EAVS)."""
    df = load("turnout")
    df = as_of_filter(df, as_of)
    df = apply_filters(
        df,
        year=list(year) if isinstance(year, list | tuple | set) else year,
        state=norm_states(state),
    )
    if with_metrics and not df.empty:
        try:
            population = load("population")
        except Exception:  # noqa: BLE001 - population optional
            population = None
        df = turnout_t.turnout_metrics(df, population)
    return df.reset_index(drop=True)


def partisan_lean(
    state: str | Sequence[str] | None = None, *, as_of: DateLike | None = None
) -> pd.DataFrame:
    """state_partisan_lean per presidential year (state minus national two-party share)."""
    df = as_of_filter(load("election_results"), as_of)
    summary = elec_t.race_summary(df)
    lean = elec_t.presidential_lean(summary)
    return apply_filters(lean, state=norm_states(state)).reset_index(drop=True)


def history(
    office: str, state: str | Sequence[str] | None = None, *, as_of: DateLike | None = None
) -> pd.DataFrame:
    """Political-history features (previous share, margin, lean, rolling averages) per race."""
    df = as_of_filter(load("election_results"), as_of)
    summary = elec_t.race_summary(df)
    hist = elec_t.political_history(summary, require_office(office))
    return apply_filters(hist, state=norm_states(state)).reset_index(drop=True)
