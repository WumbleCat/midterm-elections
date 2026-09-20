"""Point-in-time feature construction for the modelling key state × election year × office.

``build_features(year, office, as_of)`` assembles every feature family from the
processed tables using only rows published on or before ``as_of``. Target
columns (the election outcome itself) are attached for convenience but are
NEVER filtered by ``as_of`` — they are labels, not features — and are null for
elections that have not been ingested.

Each build writes a Parquet file plus a JSON sidecar describing provenance
(tables, dataset ids, ingestion runs, publication cut-offs, missingness).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..dates import general_election_date
from ..exceptions import DatasetUnavailableError
from ..geo import FIFTY_STATES, FIFTY_STATES_DC, STATE_BY_ABBR
from ..logging import get_logger
from ..paths import DataPaths, get_paths
from ..quality.point_in_time import (
    DateLike,
    assert_no_future_rows,
    filter_as_of,
    latest_as_of,
    to_date,
)
from ..storage.parquet import read_table, write_parquet_atomic
from . import candidates as cand_t
from . import demographics as demo_t
from . import economics as econ_t
from . import elections as elec_t
from . import polls as polls_t
from . import turnout as turnout_t

log = get_logger("features")

OFFICES = ("president", "senate", "house")

TARGET_COLUMNS = [
    "dem_votes",
    "rep_votes",
    "other_votes",
    "total_votes",
    "total_candidate_votes",
    "dem_vote_share",
    "rep_vote_share",
    "dem_two_party_share",
    "dem_rep_margin",
    "winner_party",
    "winning_margin",
    "dem_candidate",
    "rep_candidate",
    "uncontested",
]

FAMILIES = (
    "targets",
    "political_history",
    "turnout",
    "demographics",
    "population",
    "geography",
    "urban_rural",
    "labor",
    "industry",
    "state_economy",
    "national_economy",
    "incumbency",
    "finance",
    "race_polls",
    "approval",
    "generic_ballot",
    "special_elections",
    "naep",
    "religion",
)


@dataclass
class FeatureBuild:
    frame: pd.DataFrame
    year: int
    office: str
    as_of: dt.date
    election_date: dt.date
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def families_available(self) -> list[str]:
        return [k for k, v in self.metadata.get("families", {}).items() if v.get("available")]

    @property
    def families_unavailable(self) -> list[str]:
        return [k for k, v in self.metadata.get("families", {}).items() if not v.get("available")]

    def summary(self) -> str:
        lines = [
            f"features: {self.office} {self.year} as_of={self.as_of} rows={len(self.frame)} columns={self.frame.shape[1]}",
            f"available families: {', '.join(self.families_available)}",
            f"unavailable families: {', '.join(self.families_unavailable) or '-'}",
        ]
        if self.path:
            lines.append(f"written: {self.path}")
        return "\n".join(lines)


def _load(table: str, paths: DataPaths) -> pd.DataFrame:
    return read_table(table, paths, missing_ok=True)


def _provenance(df: pd.DataFrame, as_of: DateLike | None = None) -> dict[str, Any]:
    if df is None or df.empty:
        return {"available": False, "rows": 0}
    info: dict[str, Any] = {
        "available": True,
        "rows": int(len(df)),
        "datasets": sorted(df["dataset_id"].dropna().unique().tolist())
        if "dataset_id" in df
        else [],
        "ingestion_runs": sorted(df["ingestion_run_id"].dropna().unique().tolist())[:20]
        if "ingestion_run_id" in df
        else [],
    }
    if "publication_date" in df:
        pub = pd.to_datetime(df["publication_date"], errors="coerce")
        info["max_publication_date"] = None if pub.dropna().empty else str(pub.max().date())
        if "publication_date_estimated" in df:
            info["publication_date_estimated_share"] = round(
                float(df["publication_date_estimated"].fillna(False).mean()), 3
            )
    if as_of is not None:
        info["as_of"] = str(to_date(as_of))
    return info


def _race_key(office: str) -> list[str]:
    return ["state", "district"] if office == "house" else ["state"]


def _race_universe(
    office: str, year: int, summary: pd.DataFrame, candidates: pd.DataFrame, as_of: DateLike
) -> pd.DataFrame:
    """The set of races to build rows for."""
    key = _race_key(office)
    target = summary[
        (summary["year"] == year)
        & (summary["office"] == office)
        & (~summary["special"].fillna(False))
    ]
    if not target.empty:
        return target[key].drop_duplicates().reset_index(drop=True)
    if office == "president":
        return pd.DataFrame({"state": list(FIFTY_STATES_DC)})
    if not candidates.empty:
        c = candidates[(candidates["office"] == office) & (candidates["cycle"] == year)]
        c = filter_as_of(c, as_of, keep_unknown=True)
        c = c[c["candidate_status"].fillna("C").isin(["C", "N"]) & c["state"].isin(FIFTY_STATES_DC)]
        if not c.empty:
            return c[key].drop_duplicates().reset_index(drop=True)
    log.warning(
        "no results or candidates for race universe; using all states",
        extra={"office": office, "year": year},
    )
    return (
        pd.DataFrame({"state": list(FIFTY_STATES)})
        if office != "house"
        else pd.DataFrame(columns=key)
    )


def build_features(
    year: int,
    office: str,
    as_of: DateLike | None = None,
    *,
    states: list[str] | None = None,
    write: bool = True,
    paths: DataPaths | None = None,
    strict: bool = True,
) -> FeatureBuild:
    """Build the modelling dataset for ``office`` races in ``year`` as of ``as_of``.

    ``as_of`` defaults to the day before the general election. ``strict`` verifies
    that no feature row was published after ``as_of`` (raises PointInTimeError).
    """
    office = office.lower()
    if office not in OFFICES:
        raise ValueError(f"office must be one of {OFFICES}")
    paths = paths or get_paths()
    election_date = general_election_date(year)
    as_of_date = to_date(as_of) if as_of is not None else election_date - dt.timedelta(days=1)
    if as_of_date > election_date:
        log.warning(
            "as_of is after election day: the build is a post-election snapshot, not a forecast",
            extra={"as_of": str(as_of_date)},
        )
    key = _race_key(office)
    families: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------- elections
    results = _load("election_results", paths)
    if results.empty:
        raise DatasetUnavailableError(
            "election_results is empty; ingest medsl-senate/medsl-president first"
        )
    summary = elec_t.race_summary(results)
    candidates = _load("candidates", paths)
    races = _race_universe(office, year, summary, candidates, as_of_date)
    if states:
        races = races[races["state"].isin([s.upper() for s in states])]
    frame = races.copy()
    frame["year"] = year
    frame["office"] = office
    if "district" not in frame.columns:
        frame["district"] = "statewide"
    frame["state_fips"] = frame["state"].map(
        lambda s: STATE_BY_ABBR[s].fips if s in STATE_BY_ABBR else None
    )
    frame["election_date"] = pd.Timestamp(election_date)
    frame["as_of"] = pd.Timestamp(as_of_date)

    # targets (labels; not filtered by as_of)
    target = summary[
        (summary["year"] == year)
        & (summary["office"] == office)
        & (~summary["special"].fillna(False))
    ]
    tcols = [c for c in TARGET_COLUMNS if c in target.columns]
    frame = frame.merge(target[[*key, *tcols]], on=key, how="left")
    families["targets"] = {**_provenance(target), "note": "labels, not filtered by as_of"}

    # political history from results published by as_of
    avail_summary = filter_as_of(summary, as_of_date)
    stub = frame[[*key, "year"]].copy()
    stub["office"] = office
    stub["special"] = False
    stub["election_date"] = pd.Timestamp(election_date)
    if "district" not in stub.columns:
        stub["district"] = "statewide"
    hist_input = pd.concat(
        [avail_summary[avail_summary["year"] < year], stub], ignore_index=True, sort=False
    )
    hist = elec_t.political_history(hist_input, office)
    hist = hist[hist["year"] == year].drop(
        columns=["year", "office", "election_date"], errors="ignore"
    )
    if office != "house" and "district" in hist.columns:
        hist = hist.drop(columns=["district"])
    frame = frame.merge(hist, on=key, how="left")
    families["political_history"] = _provenance(
        avail_summary[avail_summary["year"] < year], as_of_date
    )

    # ------------------------------------------------------------ turnout
    turnout = _load("turnout", paths)
    population = _load("population", paths)
    if not turnout.empty:
        t_avail = filter_as_of(turnout, as_of_date)
        pop_avail = filter_as_of(population, as_of_date) if not population.empty else None
        metrics = turnout_t.turnout_metrics(t_avail, pop_avail) if not t_avail.empty else t_avail
        if not metrics.empty:
            prev = turnout_t.previous_turnout(metrics, office)
            # the most recent same-cycle-type election strictly before `year`
            same_cycle = prev[(prev["year"] < year) & ((prev["year"] % 4 == 0) == (year % 4 == 0))]
            last = same_cycle.sort_values("year").groupby("state", as_index=False).tail(1)
            tcols_turn = [
                "state",
                "year",
                "turnout_registered",
                "registered_voters",
                "ballots_cast",
            ] + [
                c
                for c in (
                    "turnout_population",
                    "turnout_cvap",
                    "mail_vote_share",
                    "early_vote_share",
                )
                if c in last.columns
            ]
            last = last[tcols_turn].rename(
                columns={
                    c: (f"prev_{c}" if c != "year" else "prev_turnout_year")
                    for c in tcols_turn
                    if c != "state"
                }
            )
            frame = frame.merge(last, on="state", how="left")
        families["turnout"] = _provenance(t_avail, as_of_date)
    else:
        families["turnout"] = {"available": False, "rows": 0}

    # ------------------------------------------------------- demographics
    demographics = _load("demographics", paths)
    d = (
        demo_t.demographics_as_of(demographics, as_of_date)
        if not demographics.empty
        else pd.DataFrame()
    )
    if not d.empty:
        frame = frame.merge(d, on="state", how="left")
    families["demographics"] = _provenance(
        filter_as_of(demographics, as_of_date) if not demographics.empty else demographics,
        as_of_date,
    )

    p = demo_t.population_as_of(population, as_of_date) if not population.empty else pd.DataFrame()
    geography = _load("geography", paths)
    if not p.empty:
        p = demo_t.density_features(p, geography, as_of_date) if not geography.empty else p
        frame = frame.merge(p, on="state", how="left")
    families["population"] = _provenance(
        filter_as_of(population, as_of_date) if not population.empty else population, as_of_date
    )
    families["geography"] = _provenance(
        filter_as_of(geography, as_of_date) if not geography.empty else geography, as_of_date
    )

    urban = _load("urban_rural", paths)
    u = demo_t.urban_features(urban, as_of_date) if not urban.empty else pd.DataFrame()
    if not u.empty:
        frame = frame.merge(u, on="state", how="left")
    families["urban_rural"] = _provenance(
        filter_as_of(urban, as_of_date) if not urban.empty else urban, as_of_date
    )

    # ---------------------------------------------------------- economics
    labor = _load("labor", paths)
    if not labor.empty:
        lf = econ_t.unemployment_features(labor, as_of_date)
        if not lf.empty:
            frame = frame.merge(lf, on="state", how="left")
    families["labor"] = _provenance(
        filter_as_of(labor, as_of_date) if not labor.empty else labor, as_of_date
    )

    industry = _load("industry", paths)
    if not industry.empty:
        ind = econ_t.industry_shares(industry, as_of_date)
        if not ind.empty:
            frame = frame.merge(ind, on="state", how="left")
    families["industry"] = _provenance(
        filter_as_of(industry, as_of_date) if not industry.empty else industry, as_of_date
    )

    econ = _load("state_economy", paths)
    if not econ.empty:
        se = econ_t.state_economy_features(econ, as_of_date)
        if not se.empty:
            frame = frame.merge(se, on="state", how="left")
    families["state_economy"] = _provenance(
        filter_as_of(econ, as_of_date) if not econ.empty else econ, as_of_date
    )

    national = _load("national_economy", paths)
    if not national.empty:
        nat = econ_t.national_features(national, as_of_date)
        for k, v in nat.items():
            frame[k] = v
    families["national_economy"] = _provenance(
        filter_as_of(national, as_of_date) if not national.empty else national, as_of_date
    )

    # --------------------------------------------------------- candidates
    if not candidates.empty:
        inc = cand_t.incumbency_features(candidates, year, office, as_of_date)
        if not inc.empty:
            frame = frame.merge(inc, on=key, how="left")
    families["incumbency"] = _provenance(
        filter_as_of(candidates, as_of_date, keep_unknown=True)
        if not candidates.empty
        else candidates,
        as_of_date,
    )

    finance = _load("candidate_finance", paths)
    if not finance.empty:
        fin = cand_t.finance_features(finance, year, office, as_of_date)
        if not fin.empty:
            frame = frame.merge(fin, on=key, how="left")
    if not finance.empty:
        cyc = finance[finance["cycle"] == year]
        usable = cyc[
            pd.to_datetime(cyc["retrieval_date"], errors="coerce") <= pd.Timestamp(as_of_date)
        ]
        fam = _provenance(filter_as_of(usable, as_of_date), as_of_date)
        if fam["rows"] == 0:
            fam["note"] = (
                "no finance snapshot retrieved on/before as_of (bulk summaries are post-hoc snapshots); see fec-committee-reports in ROADMAP"
            )
    else:
        fam = {"available": False, "rows": 0}
    families["finance"] = fam

    # -------------------------------------------------------------- polls
    polls = _load("polls", paths)
    if not polls.empty:
        rp = polls_t.race_poll_features(polls, year, office, as_of_date, election_date)
        if not rp.empty:
            frame = frame.merge(rp, on=key, how="left")
    families["race_polls"] = _provenance(
        filter_as_of(polls, as_of_date) if not polls.empty else polls, as_of_date
    )

    approval = _load("approval_polls", paths)
    if not approval.empty:
        for k, v in polls_t.approval_features(approval, as_of_date).items():
            frame[k] = v
    families["approval"] = _provenance(
        filter_as_of(approval, as_of_date) if not approval.empty else approval, as_of_date
    )

    generic = _load("generic_ballot_polls", paths)
    if not generic.empty:
        for k, v in polls_t.generic_ballot_features(generic, as_of_date).items():
            frame[k] = v
    families["generic_ballot"] = _provenance(
        filter_as_of(generic, as_of_date) if not generic.empty else generic, as_of_date
    )

    specials = _load("special_elections", paths)
    if not specials.empty:
        for k, v in polls_t.special_election_swing(specials, as_of_date).items():
            frame[k] = v
    families["special_elections"] = _provenance(
        filter_as_of(specials, as_of_date) if not specials.empty else specials, as_of_date
    )

    # ------------------------------------------------------ supplementary
    naep = _load("naep", paths)
    if not naep.empty:
        n = latest_as_of(
            naep, as_of_date, keys=["state", "grade", "subject"], order_col="assessment_year"
        )
        if not n.empty:
            n["col"] = (
                "naep_" + n["subject"].astype(str).str[:4] + "_grade" + n["grade"].astype(str)
            )
            wide = n.pivot_table(
                index="state", columns="col", values="average_score", aggfunc="first"
            ).reset_index()
            wide.columns.name = None
            wide["naep_year"] = (
                n.groupby("state")["assessment_year"].max().reindex(wide["state"]).values
            )
            frame = frame.merge(wide, on="state", how="left")
    families["naep"] = _provenance(
        filter_as_of(naep, as_of_date) if not naep.empty else naep, as_of_date
    )

    religion = _load("religion", paths)
    if not religion.empty:
        r = latest_as_of(religion, as_of_date, keys=["state"], order_col="survey_year")
        if not r.empty:
            rcols = ["state", "survey_year", *[c for c in r.columns if c.startswith("pct_")]]
            frame = frame.merge(
                r[rcols].rename(columns={"survey_year": "religion_survey_year"}),
                on="state",
                how="left",
            )
    families["religion"] = _provenance(
        filter_as_of(religion, as_of_date) if not religion.empty else religion, as_of_date
    )

    # ------------------------------------------------------------ finish
    frame = frame.sort_values(key).reset_index(drop=True)
    if strict:
        _verify_no_leakage(families, as_of_date)
    missing = frame.isna().mean().sort_values(ascending=False)
    metadata = {
        "year": year,
        "office": office,
        "as_of": str(as_of_date),
        "election_date": str(election_date),
        "built_at": dt.datetime.now(dt.UTC).isoformat(),
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "families": families,
        "target_columns": tcols,
        "missingness": {k: round(float(v), 3) for k, v in missing.items() if v > 0},
    }
    build = FeatureBuild(
        frame=frame,
        year=year,
        office=office,
        as_of=as_of_date,
        election_date=election_date,
        metadata=metadata,
    )
    if write:
        stem = f"{office}_{year}_asof_{as_of_date.isoformat()}"
        paths.features.mkdir(parents=True, exist_ok=True)
        build.path = write_parquet_atomic(frame, paths.features / f"{stem}.parquet")
        (paths.features / f"{stem}.json").write_text(
            json.dumps(metadata, indent=2, default=str), encoding="utf-8"
        )
        log.info(
            "features written",
            extra={"path": str(build.path), "rows": len(frame), "columns": frame.shape[1]},
        )
    return build


def _verify_no_leakage(families: dict[str, dict[str, Any]], as_of: dt.date) -> None:
    """Every non-target family's max publication date must be <= as_of."""
    for name, info in families.items():
        if name == "targets" or not info.get("available"):
            continue
        mx = info.get("max_publication_date")
        if mx and dt.date.fromisoformat(mx) > as_of:
            raise RuntimeError(
                f"family {name} contains rows published after as_of ({mx} > {as_of})"
            )


def load_features(path: Path | str) -> pd.DataFrame:
    return pd.read_parquet(path)


def audit_features(build: FeatureBuild) -> dict[str, Any]:
    """Point-in-time audit summary for a build (used by the audit skill / CLI)."""
    fam = build.metadata.get("families", {})
    return {
        "as_of": str(build.as_of),
        "election_date": str(build.election_date),
        "forecast_before_election": build.as_of < build.election_date,
        "families": {
            k: {
                "available": v.get("available"),
                "max_publication_date": v.get("max_publication_date"),
                "estimated_share": v.get("publication_date_estimated_share"),
            }
            for k, v in fam.items()
        },
        "post_as_of_families": [
            k
            for k, v in fam.items()
            if k != "targets"
            and v.get("max_publication_date")
            and dt.date.fromisoformat(v["max_publication_date"]) > build.as_of
        ],
    }


__all__ = [
    "FAMILIES",
    "FeatureBuild",
    "assert_no_future_rows",
    "audit_features",
    "build_features",
    "load_features",
]
