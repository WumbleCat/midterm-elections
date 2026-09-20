"""Turnout metrics from the EAVS-based ``turnout`` table plus population denominators."""

from __future__ import annotations

import numpy as np
import pandas as pd


def turnout_metrics(turnout: pd.DataFrame, population: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add turnout_registered, registration_rate, turnout_cvap (if CVAP present) and
    turnout_population (ballots / total population, the fallback when VAP is unknown).
    """
    out = turnout.copy()
    for c in ("ballots_cast", "registered_voters", "citizen_voting_age_population", "voting_age_population"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
    reg = out["registered_voters"].replace(0, np.nan)
    out["turnout_registered"] = out["ballots_cast"] / reg
    if "citizen_voting_age_population" in out.columns:
        cvap = out["citizen_voting_age_population"].replace(0, np.nan)
        out["turnout_cvap"] = out["ballots_cast"] / cvap
        out["registration_rate"] = out["registered_voters"] / cvap
    if "voting_age_population" in out.columns:
        out["turnout_vap"] = out["ballots_cast"] / out["voting_age_population"].replace(0, np.nan)
    if population is not None and not population.empty:
        pop = latest_population_by_year(population)
        out = out.merge(pop[["state", "year", "population"]], on=["state", "year"], how="left")
        out["turnout_population"] = out["ballots_cast"] / out["population"].replace(0, np.nan)
    if "mail_votes" in out.columns:
        out["mail_vote_share"] = out["mail_votes"] / out["ballots_cast"].replace(0, np.nan)
    if "early_votes" in out.columns:
        out["early_vote_share"] = out["early_votes"] / out["ballots_cast"].replace(0, np.nan)
    return out


def latest_population_by_year(population: pd.DataFrame) -> pd.DataFrame:
    """One population value per state-year: the most recent vintage that covers it."""
    pop = population.copy()
    pop["_v"] = pd.to_numeric(pop["revision_vintage"], errors="coerce")
    pop = pop.sort_values(["state", "year", "_v"])
    return pop.groupby(["state", "year"], as_index=False).tail(1).drop(columns=["_v"])


def previous_turnout(metrics: pd.DataFrame, office: str) -> pd.DataFrame:
    """Previous election's turnout for the same election type (presidential vs midterm)."""
    df = metrics.sort_values(["state", "year"]).copy()
    df["_cycle"] = np.where(df["year"] % 4 == 0, "presidential", "midterm")
    df["previous_turnout_registered"] = df.groupby(["state", "_cycle"])["turnout_registered"].shift(1)
    if "turnout_population" in df.columns:
        df["previous_turnout_population"] = df.groupby(["state", "_cycle"])["turnout_population"].shift(1)
    df["previous_ballots_cast"] = df.groupby(["state", "_cycle"])["ballots_cast"].shift(1)
    return df.drop(columns=["_cycle"])
