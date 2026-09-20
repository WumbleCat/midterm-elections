"""``ed.demographics`` — ACS profiles, population estimates, geography, urban/rural."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ..quality.point_in_time import DateLike
from ..transform import demographics as demo_t
from ._common import apply_filters, as_of_filter, load, norm_states


def state(
    state: str | Sequence[str] | None = None,
    year: int | Sequence[int] | None = None,
    *,
    survey: str = "acs1",
    as_of: DateLike | None = None,
) -> pd.DataFrame:
    """ACS state demographic profile (one row per state × year × survey)."""
    df = load("demographics")
    df = as_of_filter(df, as_of)
    df = apply_filters(
        df,
        state=norm_states(state),
        year=list(year) if isinstance(year, list | tuple | set) else year,
        survey=survey,
    )
    return df.reset_index(drop=True)


def population(
    state: str | Sequence[str] | None = None,
    year: int | Sequence[int] | None = None,
    *,
    vintage: str | int | None = None,
    as_of: DateLike | None = None,
    latest_vintage_only: bool = True,
) -> pd.DataFrame:
    """Annual population and components of change (Census PEP). By default the
    newest vintage covering each year is returned; pass ``vintage`` for one vintage."""
    df = load("population")
    df = as_of_filter(df, as_of)
    df = apply_filters(
        df,
        state=norm_states(state),
        year=list(year) if isinstance(year, list | tuple | set) else year,
    )
    if vintage is not None:
        df = df[df["revision_vintage"] == str(vintage)]
    elif latest_vintage_only and not df.empty:
        df = (
            df.assign(_v=pd.to_numeric(df["revision_vintage"], errors="coerce"))
            .sort_values(["state", "year", "_v"])
            .groupby(["state", "year"], as_index=False)
            .tail(1)
            .drop(columns="_v")
        )
    return df.reset_index(drop=True)


def geography(state: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Land/water area per state (Gazetteer)."""
    return apply_filters(load("geography"), state=norm_states(state)).reset_index(drop=True)


def urban_rural(
    state: str | Sequence[str] | None = None, *, as_of: DateLike | None = None
) -> pd.DataFrame:
    """Urban/rural population shares per state (decennial classification)."""
    return apply_filters(
        as_of_filter(load("urban_rural"), as_of), state=norm_states(state)
    ).reset_index(drop=True)


def snapshot(as_of: DateLike, state: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Latest demographics + population + density + urban share available as of a date."""
    frames = []
    try:
        frames.append(demo_t.demographics_as_of(load("demographics"), as_of))
    except Exception:  # noqa: BLE001
        pass
    pop = demo_t.population_as_of(load("population"), as_of)
    try:
        pop = demo_t.density_features(pop, load("geography"), as_of)
    except Exception:  # noqa: BLE001
        pass
    frames.append(pop)
    try:
        frames.append(demo_t.urban_features(load("urban_rural"), as_of))
    except Exception:  # noqa: BLE001
        pass
    out = frames[0]
    for f in frames[1:]:
        if not f.empty:
            out = out.merge(f, on="state", how="outer") if not out.empty else f
    return apply_filters(out, state=norm_states(state)).reset_index(drop=True)
