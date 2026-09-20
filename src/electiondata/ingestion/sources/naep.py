"""NAEP Data Service connector (state average scores and achievement levels)."""

from __future__ import annotations

import json

import pandas as pd

from ...exceptions import ParserError, SchemaChangeError
from ...geo import FIFTY_STATES_DC, add_state_columns
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

NAEP_URL = "https://www.nationsreportcard.gov/DataService/GetAdhocData.aspx"
SUBJECTS = {"mathematics": "MRPCM", "reading": "RRPCM"}
GRADES = (4, 8)
STATTYPES = "MN:MN,ALD:BB,ALD:BA,ALD:PR,ALD:AD"
# State NAEP mathematics/reading assessment years (main NAEP, grades 4 and 8).
NAEP_YEARS = (2003, 2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2022, 2024)


def naep_params(subject: str, grade: int, years: list[int]) -> dict[str, str]:
    return {
        "type": "data",
        "subject": subject,
        "grade": str(grade),
        "subscale": SUBJECTS[subject],
        "variable": "TOTAL",
        "jurisdiction": ",".join(FIFTY_STATES_DC),
        "stattype": STATTYPES,
        "Year": ",".join(str(y) for y in years),
    }


def parse_naep_payload(payload: dict) -> pd.DataFrame:
    if payload.get("status") != 200 or "result" not in payload:
        raise ParserError(f"NAEP response not OK: {str(payload)[:200]}")
    rows = payload["result"]
    if not rows:
        return pd.DataFrame(columns=["year", "grade", "subject", "jurisdiction", "stattype", "value", "errorFlag"])
    df = pd.DataFrame(rows)
    need = {"year", "grade", "subject", "jurisdiction", "stattype", "value"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"NAEP payload missing {sorted(need - set(df.columns))}")
    return df


_SUBJECT_CODES = {"MAT": "mathematics", "RED": "reading"}


def normalize_naep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if "isStatDisplayable" in df.columns:
        df.loc[pd.to_numeric(df["isStatDisplayable"], errors="coerce") == 0, "value"] = pd.NA
    df["subject_name"] = df["subject"].map(lambda s: _SUBJECT_CODES.get(str(s).upper(), str(s).lower()))
    wide = df.pivot_table(index=["jurisdiction", "year", "grade", "subject_name"], columns="stattype", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    wide = add_state_columns(wide, "jurisdiction")
    wide = wide[wide["state"].notna()]
    out = pd.DataFrame(
        {
            "state": wide["state"],
            "state_fips": wide["state_fips"],
            "state_name": wide["state_name"],
            "assessment_year": wide["year"].astype(int),
            "grade": wide["grade"].astype(int),
            "subject": wide["subject_name"],
            "average_score": wide.get("MN:MN"),
        }
    )
    bb = wide.get("ALD:BB")
    pr = wide.get("ALD:PR")
    ad = wide.get("ALD:AD")
    out["pct_at_or_above_basic"] = (100 - bb) / 100 if bb is not None else pd.NA
    out["pct_at_or_above_proficient"] = (pr + ad) / 100 if pr is not None and ad is not None else pd.NA
    out["pct_advanced"] = ad / 100 if ad is not None else pd.NA
    out["observation_date"] = out["assessment_year"].map(lambda y: pd.Timestamp(int(y), 3, 1))
    out["period_start"] = out["assessment_year"].map(lambda y: pd.Timestamp(int(y), 1, 1))
    out["period_end"] = out["assessment_year"].map(lambda y: pd.Timestamp(int(y), 3, 31))
    out["publication_date"] = out["assessment_year"].map(lambda y: pd.Timestamp(release_calendar.naep(int(y))))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = out["assessment_year"].astype(str)
    return out.reset_index(drop=True)


class NaepStateConnector(Connector):
    dataset_id = "naep-state"

    def _years(self, ctx: IngestContext) -> list[int]:
        years = ctx.option("years")
        if years:
            if isinstance(years, str):
                years = [int(y) for y in years.split(",") if y.strip()]
            return sorted(int(y) for y in years)
        return list(NAEP_YEARS)

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        artifacts = []
        years = self._years(ctx)
        for subject in SUBJECTS:
            for grade in GRADES:
                params = naep_params(subject, grade, years)
                resp = ctx.http.get(NAEP_URL, params=params)
                art = ctx.write_bytes(
                    resp.content,
                    f"naep_{subject}_grade{grade}.json",
                    url=NAEP_URL,
                    params=params,
                    http_status=resp.status_code,
                    note=f"NAEP {subject} grade {grade} {years[0]}-{years[-1]}",
                )
                artifacts.append(art)
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            if art.path.suffix != ".json":
                continue
            payload = json.loads(art.path.read_text(encoding="utf-8"))
            frames.append(parse_naep_payload(payload))
        if not frames:
            raise ParserError("no NAEP artifacts")
        out = normalize_naep(pd.concat(frames, ignore_index=True))
        out["source_url"] = NAEP_URL
        return out
