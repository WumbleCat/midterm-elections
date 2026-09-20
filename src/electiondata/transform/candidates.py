"""Candidate features: incumbency and campaign finance aggregated to race level, as of a date."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..quality.point_in_time import DateLike, filter_as_of, to_date


def _race_key(office: str) -> list[str]:
    return ["state", "district"] if office == "house" else ["state"]


def incumbency_features(candidates: pd.DataFrame, year: int, office: str, as_of: DateLike | None = None) -> pd.DataFrame:
    """dem_incumbent / rep_incumbent / open_seat per race from the FEC candidate master.

    Uses candidates whose election_year == year and candidate_status in (C, N)
    (statutory or not-yet-qualified) to exclude prior-cycle records.
    """
    df = candidates[(candidates["office"] == office) & (candidates["cycle"] == year)]
    if as_of is not None:
        df = filter_as_of(df, as_of, keep_unknown=True)
    df = df[df["election_year"].fillna(year) == year]
    df = df[df["candidate_status"].fillna("C").isin(["C", "N"])]
    key = _race_key(office)
    if df.empty:
        return pd.DataFrame(columns=[*key, "dem_incumbent", "rep_incumbent", "open_seat", "incumbent_party", "n_dem_candidates", "n_rep_candidates"])
    inc = df[df["incumbent_challenger_status"] == "I"]
    out = df.groupby(key).agg(
        n_dem_candidates=("party", lambda s: int((s == "DEM").sum())),
        n_rep_candidates=("party", lambda s: int((s == "REP").sum())),
    ).reset_index()
    inc_party = inc.groupby(key)["party"].agg(lambda s: "DEM" if (s == "DEM").any() else ("REP" if (s == "REP").any() else "OTHER"))
    out = out.merge(inc_party.rename("incumbent_party").reset_index(), on=key, how="left")
    open_seat = df.groupby(key)["incumbent_challenger_status"].agg(lambda s: bool((s == "O").any()) and not (s == "I").any())
    out = out.merge(open_seat.rename("open_seat").reset_index(), on=key, how="left")
    out["dem_incumbent"] = out["incumbent_party"] == "DEM"
    out["rep_incumbent"] = out["incumbent_party"] == "REP"
    out["open_seat"] = out["open_seat"].fillna(out["incumbent_party"].isna())
    return out


def finance_features(finance: pd.DataFrame, year: int, office: str, as_of: DateLike) -> pd.DataFrame:
    """Race-level fundraising as of ``as_of``: top DEM and REP candidate totals (by receipts),
    dem_fundraising_share, log receipts, cash on hand and spending.

    Only snapshots retrieved on or before ``as_of`` are used (see the comment in the
    body); within the snapshot only reports with publication_date <= as_of count.
    For historical cycles ingested after the election these features are therefore
    null unless a pre-election snapshot exists in the raw archive.
    """
    df = finance[(finance["office"] == office) & (finance["cycle"] == year)]
    key = _race_key(office)
    # A financial-summary file is a snapshot of *all* candidates at retrieval time.
    # Truncating a later snapshot to reports dated <= as_of would keep only candidates
    # who stopped filing (drop-outs) and silently drop the nominees, so a snapshot is
    # usable only if it was itself retrieved on or before as_of.
    if not df.empty:
        cutoff = pd.Timestamp(to_date(as_of))
        snapshots = pd.to_datetime(df["retrieval_date"], errors="coerce")
        df = df[snapshots <= cutoff]
        if not df.empty:
            latest_snapshot = snapshots[snapshots <= cutoff].max()
            df = df[snapshots[snapshots <= cutoff].reindex(df.index) == latest_snapshot]
    df = filter_as_of(df, as_of)
    cols = [*key, "dem_receipts", "rep_receipts", "dem_disbursements", "rep_disbursements", "dem_cash_on_hand", "rep_cash_on_hand", "dem_individual_contributions", "rep_individual_contributions", "dem_fundraising_share", "log_dem_receipts", "log_rep_receipts", "finance_coverage_end", "finance_dem_candidate_id", "finance_rep_candidate_id"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    # latest report per candidate as of the date, then top candidate per party per race
    df = df.sort_values(["candidate_id", "coverage_end_date", "revision_vintage"]).groupby("candidate_id", as_index=False).tail(1)
    rows = []
    for k, g in df.groupby(key):
        rec = dict(zip(key, k if isinstance(k, tuple) else (k,), strict=True))
        for party, prefix in (("DEM", "dem"), ("REP", "rep")):
            p = g[g["party"] == party].sort_values("total_receipts", ascending=False)
            if p.empty:
                rec[f"{prefix}_receipts"] = 0.0
                rec[f"{prefix}_disbursements"] = 0.0
                rec[f"{prefix}_cash_on_hand"] = 0.0
                rec[f"{prefix}_individual_contributions"] = 0.0
                rec[f"finance_{prefix}_candidate_id"] = None
                continue
            top = p.iloc[0]
            rec[f"{prefix}_receipts"] = float(top["total_receipts"] or 0)
            rec[f"{prefix}_disbursements"] = float(top["total_disbursements"] or 0)
            rec[f"{prefix}_cash_on_hand"] = float(top["cash_on_hand_end"] or 0)
            rec[f"{prefix}_individual_contributions"] = float(top["individual_contributions"] or 0)
            rec[f"finance_{prefix}_candidate_id"] = top["candidate_id"]
        rec["finance_coverage_end"] = g["coverage_end_date"].max()
        rows.append(rec)
    out = pd.DataFrame(rows)
    total = out["dem_receipts"] + out["rep_receipts"]
    out["dem_fundraising_share"] = np.where(total > 0, out["dem_receipts"] / total.replace(0, np.nan), np.nan)
    out["log_dem_receipts"] = np.log1p(out["dem_receipts"])
    out["log_rep_receipts"] = np.log1p(out["rep_receipts"])
    return out[cols]
