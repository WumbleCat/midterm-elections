"""Election transformations: candidate rows -> race summaries -> political history features.

All functions are pure (DataFrame in, DataFrame out) and deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..ingestion.sources.medsl import NON_CANDIDATE_LABELS

RACE_KEY = ["state", "state_fips", "year", "office", "district", "special"]


def race_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregate candidate-level general-election rows into one row per race.

    * ``dem_votes``/``rep_votes`` sum every DEM/REP candidate (matters for
      Louisiana-style jungle generals); ``other_votes`` is everything else,
      excluding blank/void/over/under-vote lines.
    * shares follow the specification formulas.
    """
    df = results.copy()
    if "election_type" in df.columns:
        df = df[df["election_type"].fillna("general") == "general"]
    df = df[~df["candidate"].fillna("").str.upper().isin(NON_CANDIDATE_LABELS)]
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").astype("float64").fillna(0.0)
    df["special"] = df["special"].fillna(False).astype(bool)
    df["party"] = df["party"].fillna("OTHER")

    grouped = df.groupby(RACE_KEY, dropna=False, sort=True)
    out = grouped.agg(
        election_date=("election_date", "first"),
        total_votes=("total_votes", "max"),
        n_candidates=("candidate", "nunique"),
        publication_date=("publication_date", "max"),
        publication_date_estimated=("publication_date_estimated", "max"),
        retrieval_date=("retrieval_date", "max"),
        revision_vintage=("revision_vintage", "max"),
        source=("source", "first"),
        source_url=("source_url", "first"),
        dataset_id=("dataset_id", "first"),
        ingestion_run_id=("ingestion_run_id", "first"),
    ).reset_index()

    party_votes = df.pivot_table(
        index=RACE_KEY, columns="party", values="votes", aggfunc="sum", fill_value=0.0
    )
    for p in ("DEM", "REP"):
        if p not in party_votes.columns:
            party_votes[p] = 0.0
    other_cols = [c for c in party_votes.columns if c not in ("DEM", "REP")]
    pv = pd.DataFrame(
        {
            "dem_votes": party_votes["DEM"],
            "rep_votes": party_votes["REP"],
            "other_votes": party_votes[other_cols].sum(axis=1) if other_cols else 0.0,
        }
    ).reset_index()
    out = out.merge(pv, on=RACE_KEY, how="left")

    top = (
        df.sort_values("votes", ascending=False)
        .groupby([*RACE_KEY, "party"], dropna=False)
        .head(1)[[*RACE_KEY, "party", "candidate", "votes"]]
    )
    dem_top = top[top["party"] == "DEM"].rename(columns={"candidate": "dem_candidate"})[
        [*RACE_KEY, "dem_candidate"]
    ]
    rep_top = top[top["party"] == "REP"].rename(columns={"candidate": "rep_candidate"})[
        [*RACE_KEY, "rep_candidate"]
    ]
    out = out.merge(dem_top, on=RACE_KEY, how="left").merge(rep_top, on=RACE_KEY, how="left")

    # winner: candidate (not party sum) with the most votes; margin over runner-up
    ranked = df.sort_values("votes", ascending=False).groupby(RACE_KEY, dropna=False)
    first = ranked.head(1)[[*RACE_KEY, "party", "votes"]].rename(
        columns={"party": "winner_party", "votes": "_v1"}
    )
    second_df: pd.DataFrame = ranked.nth(1)  # type: ignore[assignment]
    second = second_df[[*RACE_KEY, "votes"]].rename(columns={"votes": "_v2"})
    out = out.merge(first, on=RACE_KEY, how="left").merge(second, on=RACE_KEY, how="left")

    out = derived_metrics(out)
    out["winning_margin"] = (out["_v1"] - out["_v2"].fillna(0.0)) / out["total_candidate_votes"]
    out["uncontested"] = (out["dem_votes"] <= 0) | (out["rep_votes"] <= 0)
    out = out.drop(columns=["_v1", "_v2"])
    out["observation_date"] = out["election_date"]
    out["period_start"] = out["election_date"]
    out["period_end"] = out["election_date"]
    return out


def derived_metrics(summary: pd.DataFrame) -> pd.DataFrame:
    """Vote shares, two-party shares and margin from dem/rep/other vote totals."""
    out = summary.copy()
    for c in ("dem_votes", "rep_votes", "other_votes"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64").fillna(0.0)
    out["total_candidate_votes"] = out["dem_votes"] + out["rep_votes"] + out["other_votes"]
    tcv = out["total_candidate_votes"].replace(0, np.nan)
    two = (out["dem_votes"] + out["rep_votes"]).replace(0, np.nan)
    out["dem_vote_share"] = out["dem_votes"] / tcv
    out["rep_vote_share"] = out["rep_votes"] / tcv
    out["other_vote_share"] = out["other_votes"] / tcv
    out["dem_two_party_share"] = out["dem_votes"] / two
    out["rep_two_party_share"] = out["rep_votes"] / two
    out["dem_rep_margin"] = out["dem_two_party_share"] - out["rep_two_party_share"]
    return out


def national_two_party_share(pres_summary: pd.DataFrame) -> pd.DataFrame:
    """National Democratic two-party share per presidential year (sum of state votes)."""
    pres = pres_summary[
        (pres_summary["office"] == "president") & (~pres_summary["special"].fillna(False))
    ]
    nat = pres.groupby("year", as_index=False)[["dem_votes", "rep_votes"]].sum()
    nat["national_dem_two_party_share"] = nat["dem_votes"] / (nat["dem_votes"] + nat["rep_votes"])
    return nat[["year", "national_dem_two_party_share"]]


def presidential_lean(pres_summary: pd.DataFrame) -> pd.DataFrame:
    """state_partisan_lean = state dem two-party share - national dem two-party share, per presidential year.

    Also returns a smoothed lean: 0.6*latest + 0.3*previous + 0.1*third-previous
    (falls back to the available terms, re-weighted).
    """
    pres = pres_summary[
        (pres_summary["office"] == "president") & (~pres_summary["special"].fillna(False))
    ].copy()
    nat = national_two_party_share(pres_summary)
    pres = pres.merge(nat, on="year", how="left")
    pres["state_partisan_lean"] = pres["dem_two_party_share"] - pres["national_dem_two_party_share"]
    pres = pres.sort_values(["state", "year"])
    lean = pres[
        [
            "state",
            "year",
            "dem_two_party_share",
            "national_dem_two_party_share",
            "state_partisan_lean",
            "election_date",
            "publication_date",
        ]
    ].copy()
    lean = lean.rename(columns={"dem_two_party_share": "pres_dem_two_party_share"})
    grp = lean.groupby("state")["state_partisan_lean"]
    l1, l2, l3 = lean["state_partisan_lean"], grp.shift(1), grp.shift(2)
    weights = pd.DataFrame({"w1": 0.6 * l1.notna(), "w2": 0.3 * l2.notna(), "w3": 0.1 * l3.notna()})
    num = 0.6 * l1.fillna(0) + 0.3 * l2.fillna(0) + 0.1 * l3.fillna(0)
    lean["weighted_state_lean"] = num / weights.sum(axis=1).replace(0, np.nan)
    return lean.reset_index(drop=True)


def previous_same_office(summary: pd.DataFrame, office: str) -> pd.DataFrame:
    """For each state/office race, attach the previous election's outcome for the same seat.

    Senate seats are matched by class (approximated as the most recent regular
    election in the same state for that office 6 years earlier; if none, the
    most recent regular election). House uses the same district.
    """
    df = summary[(summary["office"] == office) & (~summary["special"].fillna(False))].copy()
    df = df.sort_values(["state", "district", "year"])
    cols = [
        "dem_two_party_share",
        "dem_vote_share",
        "rep_vote_share",
        "dem_rep_margin",
        "winner_party",
        "total_candidate_votes",
        "year",
    ]
    out_rows = []
    for (state, district), g in df.groupby(["state", "district"], sort=False):
        g = g.sort_values("year")
        years = g["year"].tolist()
        for _, row in g.iterrows():
            y = row["year"]
            candidates = [yy for yy in years if yy < y]
            if office == "senate":
                exact = [yy for yy in candidates if y - yy == 6]
                prev_year = exact[-1] if exact else (candidates[-1] if candidates else None)
            else:
                prev_year = candidates[-1] if candidates else None
            rec = {"state": state, "district": district, "office": office, "year": y}
            if prev_year is not None:
                prev = g[g["year"] == prev_year].iloc[0]
                for c in cols:
                    rec[f"prev_{c}"] = prev[c]
            out_rows.append(rec)
    out = pd.DataFrame(out_rows)
    if not out.empty:
        out = out.rename(columns={"prev_year": "prev_election_year"})
        out["previous_swing"] = None
    return out


def political_history(summary: pd.DataFrame, office: str) -> pd.DataFrame:
    """State-level political history features available *before* the election in ``year``.

    Columns: prev_dem_share (same office), prev_rep_share, prev_margin, prev_winner_party,
    prev_election_year, state_partisan_lean (most recent presidential election strictly
    before the election year), pres_dem_two_party_share, weighted_state_lean,
    average_dem_share_last_2/3 (same office), previous_swing.
    """
    prev = previous_same_office(summary, office)
    lean = presidential_lean(summary)
    races = summary[(summary["office"] == office) & (~summary["special"].fillna(False))][
        ["state", "district", "year", "election_date"]
    ].drop_duplicates()
    out = races.merge(prev, on=["state", "district", "year"], how="left")
    # most recent presidential lean strictly before the election year
    out["state"] = out["state"].astype("string")
    lean_cols = lean[
        [
            "state",
            "year",
            "state_partisan_lean",
            "pres_dem_two_party_share",
            "national_dem_two_party_share",
            "weighted_state_lean",
        ]
    ].rename(columns={"year": "lean_year"})
    lean_cols["state"] = lean_cols["state"].astype("string")
    m = out[["state", "district", "year"]].merge(lean_cols, on="state", how="left")
    m = m[m["lean_year"] < m["year"]]
    m = m.sort_values("lean_year").groupby(["state", "district", "year"], as_index=False).tail(1)
    merged = out.merge(m, on=["state", "district", "year"], how="left")
    # rolling averages of the same office's previous results
    same = summary[(summary["office"] == office) & (~summary["special"].fillna(False))].sort_values(
        ["state", "district", "year"]
    )
    same["average_dem_share_last_2"] = same.groupby(["state", "district"])[
        "dem_two_party_share"
    ].transform(lambda s: s.shift(1).rolling(2, min_periods=1).mean())
    same["average_dem_share_last_3"] = same.groupby(["state", "district"])[
        "dem_two_party_share"
    ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    same["previous_swing"] = same.groupby(["state", "district"])["dem_two_party_share"].transform(
        lambda s: s.shift(1) - s.shift(2)
    )
    merged = merged.drop(columns=["previous_swing"], errors="ignore").merge(
        same[
            [
                "state",
                "district",
                "year",
                "average_dem_share_last_2",
                "average_dem_share_last_3",
                "previous_swing",
            ]
        ],
        on=["state", "district", "year"],
        how="left",
    )
    rename = {
        "prev_dem_two_party_share": "prev_dem_share",
        "prev_rep_vote_share": "prev_rep_share",
        "prev_dem_rep_margin": "prev_margin",
        "prev_total_candidate_votes": "prev_total_candidate_votes",
    }
    return merged.rename(columns=rename).reset_index(drop=True)
