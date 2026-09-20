"""``ed.economics`` — labour market, industry, state economy and national series."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..quality.point_in_time import DateLike, to_date
from ..transform import economics as econ_t
from ._common import apply_filters, as_of_filter, load, norm_states


def labor(
    state: str | Sequence[str] | None = None,
    *,
    start: DateLike | None = None,
    end: DateLike | None = None,
    as_of: DateLike | None = None,
    seasonally_adjusted: bool = True,
) -> pd.DataFrame:
    """Monthly LAUS series (labor_force, employment, unemployment, unemployment_rate)."""
    df = load("labor")
    df = as_of_filter(df, as_of)
    df = apply_filters(df, state=norm_states(state), seasonally_adjusted=seasonally_adjusted)
    if start is not None:
        df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(to_date(start))]
    if end is not None:
        df = df[pd.to_datetime(df["date"]) <= pd.Timestamp(to_date(end))]
    return df.sort_values(["state", "date"]).reset_index(drop=True)


def labor_snapshot(as_of: DateLike, state: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Per-state unemployment level and 3m/12m changes as of a date."""
    df = econ_t.unemployment_features(load("labor"), as_of)
    return apply_filters(df, state=norm_states(state)).reset_index(drop=True)


def industry(
    state: str | Sequence[str] | None = None,
    year: int | Sequence[int] | None = None,
    *,
    as_of: DateLike | None = None,
    shares: bool = False,
) -> pd.DataFrame:
    """QCEW annual employment/wages by industry; ``shares=True`` returns industry employment shares."""
    df = as_of_filter(load("industry"), as_of)
    if shares:
        out = econ_t.industry_shares(df, as_of or "2999-12-31")
        return apply_filters(out, state=norm_states(state)).reset_index(drop=True)
    df = apply_filters(
        df,
        state=norm_states(state),
        year=list(year) if isinstance(year, list | tuple | set) else year,
    )
    return df.reset_index(drop=True)


def state_economy(
    state: str | Sequence[str] | None = None,
    year: int | Sequence[int] | None = None,
    *,
    measure: str | Sequence[str] | None = None,
    as_of: DateLike | None = None,
) -> pd.DataFrame:
    """BEA annual GDP / personal income / RPP (long format)."""
    df = as_of_filter(load("state_economy"), as_of)
    df = apply_filters(
        df,
        state=norm_states(state),
        year=list(year) if isinstance(year, list | tuple | set) else year,
        measure=list(measure) if isinstance(measure, list | tuple | set) else measure,
    )
    return df.reset_index(drop=True)


def national(
    *,
    measure: str | Sequence[str] | None = None,
    as_of: DateLike | None = None,
    wide: bool = False,
) -> pd.DataFrame:
    """Monthly national series (CPI, payrolls, earnings, unemployment, participation)."""
    df = as_of_filter(load("national_economy"), as_of)
    df = apply_filters(
        df, measure=list(measure) if isinstance(measure, list | tuple | set) else measure
    )
    if wide:
        w = df.pivot_table(
            index="date",
            columns=["measure", "seasonally_adjusted"],
            values="value",
            aggfunc="first",
        )
        w.columns = [f"{col[0]}_{'sa' if col[1] else 'nsa'}" for col in w.columns.tolist()]
        return w.reset_index()
    return df.sort_values(["measure", "date"]).reset_index(drop=True)


def national_snapshot(as_of: DateLike) -> dict[str, float | None]:
    """National conditions as of a date (unemployment, CPI y/y, payroll growth, wages)."""
    return econ_t.national_features(load("national_economy"), as_of)
