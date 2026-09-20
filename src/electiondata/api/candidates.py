"""``ed.candidates`` — FEC candidates, incumbency and campaign finance."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..quality.point_in_time import DateLike
from ..transform import candidates as cand_t
from ._common import apply_filters, as_of_filter, latest_vintage, load, norm_office, norm_states


def candidates(
    year: int | None = None,
    state: str | Sequence[str] | None = None,
    office: str | None = None,
    *,
    as_of: DateLike | None = None,
    status: Sequence[str] | None = ("C", "N"),
) -> pd.DataFrame:
    """Registered candidates from the FEC candidate master (cycle == year)."""
    df = load("candidates")
    df = as_of_filter(df, as_of)
    df = apply_filters(df, cycle=year, state=norm_states(state), office=norm_office(office))
    if status:
        df = df[df["candidate_status"].isin(list(status))]
    return latest_vintage(df, ["candidate_id", "cycle"]).reset_index(drop=True)


def incumbency(year: int, office: str, *, as_of: DateLike | None = None) -> pd.DataFrame:
    """dem_incumbent / rep_incumbent / open_seat per race."""
    return cand_t.incumbency_features(load("candidates"), year, norm_office(office), as_of)


def finance(
    state: str | Sequence[str] | None = None,
    year: int | None = None,
    office: str | None = None,
    *,
    as_of: DateLike | None = None,
    race_level: bool = False,
) -> pd.DataFrame:
    """Candidate financial summaries (receipts, disbursements, cash on hand).

    With ``race_level=True`` returns per-race DEM/REP totals and dem_fundraising_share
    as of ``as_of`` (requires ``year`` and ``office``).
    """
    df = load("candidate_finance")
    if race_level:
        if year is None or office is None or as_of is None:
            raise ValueError("race_level=True requires year, office and as_of")
        out = cand_t.finance_features(df, year, norm_office(office), as_of)
        return apply_filters(out, state=norm_states(state)).reset_index(drop=True)
    df = as_of_filter(df, as_of)
    df = apply_filters(df, cycle=year, state=norm_states(state), office=norm_office(office))
    return df.sort_values(["cycle", "state", "total_receipts"], ascending=[True, True, False]).reset_index(drop=True)
