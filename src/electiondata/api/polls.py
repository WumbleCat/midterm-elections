"""``ed.polls`` — race polls, presidential approval, generic ballot, special elections."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..quality.point_in_time import DateLike
from ..transform import polls as polls_t
from ._common import apply_filters, as_of_filter, load, norm_office, norm_states


def races(
    year: int | None = None,
    state: str | Sequence[str] | None = None,
    office: str | None = None,
    *,
    as_of: DateLike | None = None,
    aggregate: bool = False,
) -> pd.DataFrame:
    """Poll-level race polling; ``aggregate=True`` returns per-race averages as of ``as_of``."""
    df = load("polls")
    if aggregate:
        if year is None or office is None or as_of is None:
            raise ValueError("aggregate=True requires year, office and as_of")
        out = polls_t.race_poll_features(df, year, norm_office(office), as_of)
        return apply_filters(out, state=norm_states(state)).reset_index(drop=True)
    df = as_of_filter(df, as_of)
    df = apply_filters(df, year=year, state=norm_states(state), office=norm_office(office))
    return df.sort_values("end_date").reset_index(drop=True)


def approval(*, as_of: DateLike | None = None, aggregate: bool = False) -> pd.DataFrame | dict:
    df = as_of_filter(load("approval_polls"), as_of)
    if aggregate:
        if as_of is None:
            raise ValueError("aggregate=True requires as_of")
        return polls_t.approval_features(df, as_of)
    return df.sort_values("end_date").reset_index(drop=True)


def generic_ballot(
    *, as_of: DateLike | None = None, aggregate: bool = False
) -> pd.DataFrame | dict:
    df = as_of_filter(load("generic_ballot_polls"), as_of)
    if aggregate:
        if as_of is None:
            raise ValueError("aggregate=True requires as_of")
        return polls_t.generic_ballot_features(df, as_of)
    return df.sort_values("end_date").reset_index(drop=True)


def special_elections(*, as_of: DateLike | None = None) -> pd.DataFrame:
    return as_of_filter(load("special_elections"), as_of).reset_index(drop=True)
