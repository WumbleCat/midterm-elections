"""Manual CSV adapters for poll-level data (approval, generic ballot, race polls).

No durable, freely licensed, structured poll-level source with history was
identified (see docs/DATA_SOURCES.md), so these adapters ingest CSV files the
user places in ``data/raw/polling/{dataset}/manual/``. Each CSV must use the
column names of the target schema (see the templates in ``docs/DATA_SOURCES.md``);
percentages may be given as 0-100 or 0-1 and are normalised to 0-1.

``publication_date`` is REQUIRED for every poll (the date the poll was
released) so that point-in-time filtering is exact.
"""

from __future__ import annotations

import pandas as pd

from ...exceptions import ParserError, SchemaChangeError
from ...geo import add_state_columns
from ..base import IngestContext, ManualFileConnector, RawArtifact


def _read_manual_csvs(artifacts: list[RawArtifact]) -> pd.DataFrame:
    frames = []
    for art in artifacts:
        if art.path.suffix.lower() != ".csv":
            continue
        try:
            frames.append(pd.read_csv(art.path, dtype=str, keep_default_na=False, na_values=[""]))
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"cannot read {art.path.name}: {exc}") from exc
    if not frames:
        raise ParserError("no CSV files found in the manual directory")
    return pd.concat(frames, ignore_index=True)


def _share(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors="coerce")
    return v.where(v <= 1.0, v / 100.0)


def _require(df: pd.DataFrame, cols: set[str], what: str) -> None:
    missing = cols - set(df.columns)
    if missing:
        raise SchemaChangeError(f"{what} CSV missing required columns {sorted(missing)}")


def _common_dates(out: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    out["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    out["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    out["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
    if out["publication_date"].isna().any():
        raise SchemaChangeError("every poll needs a parseable publication_date (release date)")
    out["publication_date_estimated"] = False
    out["observation_date"] = out["end_date"]
    out["period_start"] = out["start_date"]
    out["period_end"] = out["end_date"]
    return out


class ApprovalPollsConnector(ManualFileConnector):
    dataset_id = "polls-approval"
    expected_files = ("approval_polls.csv",)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        df = _read_manual_csvs(artifacts)
        _require(
            df,
            {
                "poll_id",
                "pollster",
                "start_date",
                "end_date",
                "approve",
                "disapprove",
                "publication_date",
            },
            "approval",
        )
        out = pd.DataFrame({"poll_id": df["poll_id"], "pollster": df["pollster"]})
        out["president"] = df.get("president")
        out["sample_size"] = pd.to_numeric(df.get("sample_size"), errors="coerce")
        out["population_type"] = df.get("population_type")
        out["approve"] = _share(df["approve"])
        out["disapprove"] = _share(df["disapprove"])
        out["net_approval"] = out["approve"] - out["disapprove"]
        out = _common_dates(out, df)
        out["source_url"] = df.get("source_url")
        out["revision_vintage"] = None
        return out


class GenericBallotConnector(ManualFileConnector):
    dataset_id = "polls-generic-ballot"
    expected_files = ("generic_ballot_polls.csv",)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        df = _read_manual_csvs(artifacts)
        _require(
            df,
            {
                "poll_id",
                "pollster",
                "start_date",
                "end_date",
                "generic_dem",
                "generic_rep",
                "publication_date",
            },
            "generic ballot",
        )
        out = pd.DataFrame({"poll_id": df["poll_id"], "pollster": df["pollster"]})
        out["sample_size"] = pd.to_numeric(df.get("sample_size"), errors="coerce")
        out["population_type"] = df.get("population_type")
        out["generic_dem"] = _share(df["generic_dem"])
        out["generic_rep"] = _share(df["generic_rep"])
        out["generic_other"] = _share(df["generic_other"]) if "generic_other" in df else pd.NA
        out["undecided"] = _share(df["undecided"]) if "undecided" in df else pd.NA
        out["generic_margin"] = out["generic_dem"] - out["generic_rep"]
        out = _common_dates(out, df)
        out["source_url"] = df.get("source_url")
        out["revision_vintage"] = None
        return out


class RacePollsConnector(ManualFileConnector):
    dataset_id = "polls-races"
    expected_files = ("race_polls.csv",)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        df = _read_manual_csvs(artifacts)
        _require(
            df,
            {
                "poll_id",
                "state",
                "office",
                "year",
                "pollster",
                "start_date",
                "end_date",
                "dem_pct",
                "rep_pct",
                "publication_date",
            },
            "race polls",
        )
        st = add_state_columns(df, "state")
        out = pd.DataFrame(
            {
                "poll_id": df["poll_id"],
                "state": st["state"],
                "state_fips": st["state_fips"],
                "district": df["district"].fillna("statewide") if "district" in df else "statewide",
                "office": df["office"].str.strip().str.lower(),
                "year": pd.to_numeric(df["year"], errors="coerce"),
                "pollster": df["pollster"],
                "pollster_grade": df.get("pollster_grade"),
                "sponsor": df.get("sponsor"),
                "sample_size": pd.to_numeric(df.get("sample_size"), errors="coerce"),
                "population_type": df.get("population_type"),
                "mode": df.get("mode"),
                "dem_candidate": df.get("dem_candidate"),
                "rep_candidate": df.get("rep_candidate"),
                "dem_pct": _share(df["dem_pct"]),
                "rep_pct": _share(df["rep_pct"]),
            }
        )
        out["other_pct"] = _share(df["other_pct"]) if "other_pct" in df else pd.NA
        out["undecided_pct"] = _share(df["undecided_pct"]) if "undecided_pct" in df else pd.NA
        out["poll_margin"] = out["dem_pct"] - out["rep_pct"]
        out = _common_dates(out, df)
        out["source_url"] = df.get("source_url")
        out["revision_vintage"] = None
        if out["state"].isna().any():
            bad = df.loc[out["state"].isna(), "state"].unique()[:5]
            raise SchemaChangeError(f"unmapped state values in race polls: {list(bad)}")
        return out
