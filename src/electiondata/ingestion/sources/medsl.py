"""MIT Election Data + Science Lab (MEDSL) connectors via Harvard Dataverse.

Senate and President files are public. The House file is behind a Dataverse
*guestbook* (terms acknowledgement) that the API cannot satisfy, so it is a
manual download parsed by the same normalizer.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from ...dates import general_election_date
from ...exceptions import DatasetUnavailableError, ParserError, SchemaChangeError
from ...geo import add_state_columns
from ...parties import normalize_party
from ..base import Connector, IngestContext, ManualFileConnector, RawArtifact

DATAVERSE = "https://dataverse.harvard.edu"

# Non-candidate ballot lines that must not be treated as candidates.
NON_CANDIDATE_LABELS = {
    "BLANK VOTES",
    "BLANK VOTE",
    "BLANK",
    "VOID",
    "VOID VOTES",
    "OVERVOTES",
    "OVER VOTES",
    "UNDERVOTES",
    "UNDER VOTES",
    "SCATTERING",
    "SCATTERED",
    "OTHER WRITE-INS",
}


def _detect_sep(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        head = fh.readline()
    return "\t" if head.count("\t") > head.count(",") else ","


def read_medsl_file(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            sep=_detect_sep(path),
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            quoting=csv.QUOTE_MINIMAL,
            encoding="utf-8",
            encoding_errors="replace",
        )
    except Exception as exc:  # noqa: BLE001
        raise ParserError(f"cannot read MEDSL file {path.name}: {exc}") from exc


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().isin({"TRUE", "1", "T", "YES"})


def normalize_medsl(df: pd.DataFrame, office: str, *, party_col: str) -> pd.DataFrame:
    """Map a MEDSL returns file onto the election_results schema."""
    required = {"year", "state_po", "candidate", "candidatevotes", "totalvotes", party_col}
    missing = required - set(df.columns)
    if missing:
        raise SchemaChangeError(f"MEDSL {office} file missing expected columns: {sorted(missing)}")
    out = pd.DataFrame()
    out["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    out = add_state_columns(pd.concat([out, df[["state_po"]]], axis=1), "state_po")
    out["office"] = office
    if "district" in df.columns and office == "house":
        out["district"] = df["district"].astype(str).str.strip().map(_format_district)
    else:
        out["district"] = "statewide"
    stage = (
        df["stage"].astype(str).str.strip().str.lower()
        if "stage" in df.columns
        else pd.Series("gen", index=df.index)
    )
    runoff = _bool(df["runoff"]) if "runoff" in df.columns else pd.Series(False, index=df.index)
    stage = stage.mask(runoff | stage.str.contains("runoff"), "runoff")
    stage = stage.replace({"gen": "general", "pre": "primary"})
    out["election_type"] = stage
    out["special"] = _bool(df["special"]) if "special" in df.columns else False
    out["candidate"] = df["candidate"].astype(str).str.strip().str.upper()
    out["party_raw"] = df[party_col]
    simplified = df["party_simplified"] if "party_simplified" in df.columns else df[party_col]
    out["party"] = simplified.map(normalize_party)
    out["writein"] = _bool(df["writein"]) if "writein" in df.columns else False
    out["votes"] = pd.to_numeric(df["candidatevotes"], errors="coerce")
    out["total_votes"] = pd.to_numeric(df["totalvotes"], errors="coerce")
    out["unofficial"] = _bool(df["unofficial"]) if "unofficial" in df.columns else False
    out["mode"] = (
        df["mode"].astype(str).str.strip().str.upper() if "mode" in df.columns else "TOTAL"
    )
    out["revision_vintage"] = df["version"].astype(str) if "version" in df.columns else None
    out = out[out["year"].notna()]
    out = _collapse_modes(out)
    out = _collapse_fusion(out)
    out["election_date"] = out["year"].map(lambda y: pd.Timestamp(general_election_date(int(y))))
    out["observation_date"] = out["election_date"]
    out["period_start"] = out["election_date"]
    out["period_end"] = out["election_date"]
    # Unofficial totals are known on election night; the cleaned dataset arrives later.
    out["publication_date"] = out["election_date"]
    out["publication_date_estimated"] = True
    out = out[out["election_type"] == "general"].drop(columns=["mode", "state_po"], errors="ignore")
    return out.reset_index(drop=True)


def _format_district(value: str) -> str:
    v = value.strip().lower()
    if v in {"statewide", "", "nan", "none"}:
        return "statewide"
    try:
        n = int(float(v))
    except ValueError:
        return v
    return "at-large" if n == 0 else f"{n:02d}"


_KEY = ["year", "state", "office", "district", "election_type", "special", "candidate", "party_raw"]


def _collapse_modes(df: pd.DataFrame) -> pd.DataFrame:
    """Prefer TOTAL rows; otherwise sum the vote-method rows for the same candidate line."""
    if df["mode"].nunique() <= 1:
        return df.drop(columns=["mode"])
    has_total = df.groupby(_KEY, dropna=False)["mode"].transform(lambda s: (s == "TOTAL").any())
    keep = df[(~has_total) | (df["mode"] == "TOTAL")]
    agg = {c: "first" for c in keep.columns if c not in _KEY and c != "mode"}
    agg["votes"] = "sum"
    grouped = keep.groupby(_KEY, dropna=False, as_index=False).agg(agg)
    return grouped


def _collapse_fusion(df: pd.DataFrame) -> pd.DataFrame:
    """Sum ballot lines per candidate (NY-style fusion) and take the party of the largest line."""
    key = ["year", "state", "office", "district", "election_type", "special", "candidate"]
    dup = df.duplicated(subset=key, keep=False)
    if not dup.any():
        return df
    single = df[~dup]
    multi = df[dup].sort_values("votes", ascending=False)
    agg = {c: "first" for c in multi.columns if c not in key}
    agg["votes"] = "sum"
    agg["party_raw"] = lambda s: " + ".join(str(x) for x in s)
    collapsed = multi.groupby(key, dropna=False, as_index=False).agg(agg)
    return pd.concat([single, collapsed], ignore_index=True)


class _DataverseConnector(Connector):
    doi: str
    filename_prefix: str  # e.g. "1976-2024-senate"
    office: str
    party_col: str = "party_detailed"

    def _locate_file(self, ctx: IngestContext) -> tuple[int, dict]:
        meta = ctx.http.get_json(
            f"{DATAVERSE}/api/datasets/:persistentId", params={"persistentId": f"doi:{self.doi}"}
        )
        version = meta["data"]["latestVersion"]
        for f in version["files"]:
            df_ = f["dataFile"]
            name = df_.get("originalFileName") or df_.get("filename", "")
            if name.startswith(self.filename_prefix) and name.endswith((".csv", ".tab")):
                return df_["id"], version
        raise DatasetUnavailableError(f"no file starting with {self.filename_prefix} in {self.doi}")

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        file_id, version = self._locate_file(ctx)
        meta_bytes = json.dumps(version, indent=1).encode()
        meta_art = ctx.write_bytes(
            meta_bytes,
            "dataverse_version.json",
            url=f"{DATAVERSE}/api/datasets/:persistentId?persistentId=doi:{self.doi}",
            note="Dataverse version metadata",
        )
        meta_art.extra = {
            "version": f"{version.get('versionNumber')}.{version.get('versionMinorNumber', 0)}",
            "release_time": version.get("releaseTime"),
        }
        data = ctx.download(
            f"{DATAVERSE}/api/access/datafile/{file_id}",
            f"{self.filename_prefix}.csv",
            params={"format": "original"},
            note="MEDSL returns file",
        )
        ctx.note(
            f"{self.dataset_id}: dataverse version {meta_art.extra['version']} released {meta_art.extra['release_time']}"
        )
        return [data, meta_art]

    def staging_frame(
        self, artifacts: list[RawArtifact], ctx: IngestContext
    ) -> pd.DataFrame | None:
        data = _data_artifact(artifacts, self.filename_prefix)
        return read_medsl_file(data.path)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        data = _data_artifact(artifacts, self.filename_prefix)
        raw = read_medsl_file(data.path)
        out = normalize_medsl(raw, self.office, party_col=self.party_col)
        release = _release_date(artifacts)
        if release is not None:
            out["revision_vintage"] = out["revision_vintage"].fillna(release.isoformat())
        out["source_url"] = data.url
        return out


def _data_artifact(artifacts: list[RawArtifact], prefix: str) -> RawArtifact:
    for a in artifacts:
        if a.path.name.startswith(prefix):
            return a
    raise DatasetUnavailableError(f"no raw artifact starting with {prefix}")


def _release_date(artifacts: list[RawArtifact]) -> dt.date | None:
    for a in artifacts:
        if a.path.name == "dataverse_version.json" and a.path.exists():
            try:
                meta = json.loads(a.path.read_text(encoding="utf-8"))
                rt = meta.get("releaseTime")
                return dt.date.fromisoformat(rt[:10]) if rt else None
            except (ValueError, json.JSONDecodeError):
                return None
    return None


class SenateResultsConnector(_DataverseConnector):
    dataset_id = "medsl-senate"
    doi = "10.7910/DVN/PEJ5QU"
    filename_prefix = "1976-2024-senate"
    office = "senate"


class PresidentResultsConnector(_DataverseConnector):
    dataset_id = "medsl-president"
    doi = "10.7910/DVN/42MVDX"
    filename_prefix = "1976-2024-president"
    office = "president"


class HouseResultsConnector(ManualFileConnector):
    """House returns: download ``1976-2024-house.tab`` (or .csv) from
    https://doi.org/10.7910/DVN/IG0UN2 after completing the guestbook, and place it in
    ``data/raw/medsl/medsl-house/manual/``.
    """

    dataset_id = "medsl-house"
    expected_files = ("1976-2024-house.tab or 1976-2024-house.csv",)
    office = "house"

    def _data(self, artifacts: list[RawArtifact]) -> RawArtifact:
        for a in artifacts:
            if "house" in a.path.name.lower() and a.path.suffix.lower() in {".tab", ".csv", ".tsv"}:
                return a
        raise DatasetUnavailableError(
            "no MEDSL house file (*.tab/*.csv) found in the manual directory"
        )

    def staging_frame(
        self, artifacts: list[RawArtifact], ctx: IngestContext
    ) -> pd.DataFrame | None:
        return read_medsl_file(self._data(artifacts).path)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        art = self._data(artifacts)
        raw = read_medsl_file(art.path)
        party_col = "party" if "party" in raw.columns else "party_detailed"
        out = normalize_medsl(raw, "house", party_col=party_col)
        out["source_url"] = "https://doi.org/10.7910/DVN/IG0UN2"
        return out
