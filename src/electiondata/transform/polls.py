"""Polling aggregates: date-specific averages built from poll-level observations.

Every function takes an ``as_of`` date and only uses polls whose
``publication_date`` (release date) is on or before it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..quality.point_in_time import DateLike, filter_as_of, to_date


def _window(df: pd.DataFrame, as_of: DateLike, days: int, date_col: str = "end_date") -> pd.DataFrame:
    cutoff = pd.Timestamp(to_date(as_of))
    avail = filter_as_of(df, as_of)
    end = pd.to_datetime(avail[date_col], errors="coerce")
    return avail[(end > cutoff - pd.Timedelta(days=days)) & (end <= cutoff)]


def _weighted_mean(values: pd.Series, weights: pd.Series | None) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    if v.dropna().empty:
        return None
    if weights is None or weights.isna().all():
        return float(v.mean())
    w = pd.to_numeric(weights, errors="coerce").fillna(v.dropna().shape[0] and pd.to_numeric(weights, errors="coerce").median() or 1.0)
    return float(np.average(v.fillna(v.mean()), weights=w.clip(lower=1)))


def approval_features(approval: pd.DataFrame, as_of: DateLike) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for days in (7, 30, 90):
        w = _window(approval, as_of, days)
        out[f"approval_average_{days}d"] = _weighted_mean(w["approve"], w.get("sample_size")) if not w.empty else None
        out[f"net_approval_{days}d"] = _weighted_mean(w["net_approval"], w.get("sample_size")) if not w.empty else None
    prev = _window(approval, pd.Timestamp(to_date(as_of)) - pd.Timedelta(days=30), 30)
    if out.get("approval_average_30d") is not None and not prev.empty:
        out["approval_change_30d"] = out["approval_average_30d"] - (_weighted_mean(prev["approve"], prev.get("sample_size")) or np.nan)
    else:
        out["approval_change_30d"] = None
    out["n_approval_polls_30d"] = int(len(_window(approval, as_of, 30)))
    return out


def generic_ballot_features(generic: pd.DataFrame, as_of: DateLike) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for days in (7, 30, 90):
        w = _window(generic, as_of, days)
        out[f"generic_margin_{days}d"] = _weighted_mean(w["generic_margin"], w.get("sample_size")) if not w.empty else None
    w30 = _window(generic, as_of, 30)
    out["generic_ballot_dem_30d"] = _weighted_mean(w30["generic_dem"], w30.get("sample_size")) if not w30.empty else None
    out["generic_ballot_rep_30d"] = _weighted_mean(w30["generic_rep"], w30.get("sample_size")) if not w30.empty else None
    prev = _window(generic, pd.Timestamp(to_date(as_of)) - pd.Timedelta(days=30), 30)
    if out.get("generic_margin_30d") is not None and not prev.empty:
        out["generic_change_30d"] = out["generic_margin_30d"] - (_weighted_mean(prev["generic_margin"], prev.get("sample_size")) or np.nan)
    else:
        out["generic_change_30d"] = None
    out["n_generic_polls_30d"] = int(len(w30))
    return out


def race_poll_features(polls: pd.DataFrame, year: int, office: str, as_of: DateLike, election_date: DateLike | None = None) -> pd.DataFrame:
    """Per race: 7/30-day poll-margin averages, count, dispersion and recency."""
    df = polls[(polls["year"] == year) & (polls["office"] == office)]
    key = ["state", "district"] if office == "house" else ["state"]
    cols = [*key, "state_poll_margin", "state_poll_dem", "state_poll_rep", "polling_average_7d", "polling_average_30d", "number_recent_polls", "polling_uncertainty", "poll_recency_days", "days_to_election"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    cutoff = pd.Timestamp(to_date(as_of))
    w30 = _window(df, as_of, 30)
    w7 = _window(df, as_of, 7)
    rows = []
    for k, g in filter_as_of(df, as_of).groupby(key):
        rec = dict(zip(key, k if isinstance(k, tuple) else (k,), strict=True))
        g30 = w30[(w30[key] == pd.Series(rec)).all(axis=1)] if not w30.empty else w30
        g7 = w7[(w7[key] == pd.Series(rec)).all(axis=1)] if not w7.empty else w7
        recent = g30 if not g30.empty else g.sort_values("end_date").tail(3)
        rec["state_poll_margin"] = _weighted_mean(recent["poll_margin"], recent.get("sample_size"))
        rec["state_poll_dem"] = _weighted_mean(recent["dem_pct"], recent.get("sample_size"))
        rec["state_poll_rep"] = _weighted_mean(recent["rep_pct"], recent.get("sample_size"))
        rec["polling_average_7d"] = _weighted_mean(g7["poll_margin"], g7.get("sample_size")) if not g7.empty else None
        rec["polling_average_30d"] = _weighted_mean(g30["poll_margin"], g30.get("sample_size")) if not g30.empty else None
        rec["number_recent_polls"] = int(len(g30))
        rec["polling_uncertainty"] = float(g30["poll_margin"].std()) if len(g30) > 1 else None
        last_end = pd.to_datetime(g["end_date"]).max()
        rec["poll_recency_days"] = int((cutoff - last_end).days) if pd.notna(last_end) else None
        rec["days_to_election"] = int((pd.Timestamp(to_date(election_date)) - cutoff).days) if election_date is not None else None
        rows.append(rec)
    return pd.DataFrame(rows, columns=cols)


def special_election_swing(specials: pd.DataFrame, as_of: DateLike) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    if specials is None or specials.empty:
        return {"special_election_swing_30d": None, "special_election_swing_90d": None, "special_election_swing_180d": None}
    for days in (30, 90, 180):
        w = _window(specials, as_of, days, date_col="election_date")
        out[f"special_election_swing_{days}d"] = float(w["special_election_swing"].mean()) if not w.empty else None
    return out
