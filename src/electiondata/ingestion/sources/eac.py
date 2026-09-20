"""EAC Election Administration and Voting Survey (EAVS) connector.

Public-release CSV zips have one row per local jurisdiction and hundreds of
item columns. We keep the registration (section A), mail (C), provisional (E)
and participation (F) items that map onto the ``turnout`` table and aggregate
them to state level. Negative EAVS codes (-88 not applicable, -99 data not
available, and any other negative sentinel) are treated as missing.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from ...dates import general_election_date
from ...exceptions import ParserError, SchemaChangeError
from ...geo import add_state_columns
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

# Stable public-release URLs (nolabel CSV zips). Verified 2026-09-20.
EAVS_FILES: dict[int, str] = {
    2020: "https://www.eac.gov/sites/default/files/2023-12/2020_EAVS_for_Public_Release_nolabel_V1.2_CSV.zip",
    2022: "https://www.eac.gov/sites/default/files/2023-06/2022_EAVS_for_Public_Release_nolabel_V1_CSV.zip",
    2024: "https://www.eac.gov/sites/default/files/2026-02/2024_EAVS_for_Public_Release_nolabel_V2_csv.zip",
}

ITEM_MAP: dict[str, str] = {
    "A1a": "registered_voters",
    "A1b": "active_registered_voters",
    "A1c": "inactive_registered_voters",
    "C1a": "mail_ballots_transmitted",
    "C1b": "mail_ballots_returned",
    "C4a": "mail_ballots_rejected",
    "E1a": "provisional_ballots_submitted",
    "F1a": "ballots_cast",
    "F1b": "in_person_election_day_votes",
    "F1c": "early_votes",
    "F1d": "mail_votes",
    "F1e": "provisional_votes",
    "F1f": "uocava_votes",
}


def read_eavs_zip(path) -> pd.DataFrame:  # noqa: ANN001
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ParserError(f"{path.name}: no CSV inside zip")
            with zf.open(names[0]) as fh:
                return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"), dtype=str, low_memory=False)
    except zipfile.BadZipFile as exc:
        raise ParserError(f"{path.name}: not a zip file") from exc


def normalize_eavs(df: pd.DataFrame, year: int) -> pd.DataFrame:
    required = {"State_Abbr", "A1a", "F1a"}
    missing = required - set(df.columns)
    if missing:
        raise SchemaChangeError(f"EAVS {year} file missing columns {sorted(missing)}")
    items = [c for c in ITEM_MAP if c in df.columns]
    work = df[["State_Abbr", *items]].copy()
    for c in items:
        v = pd.to_numeric(work[c], errors="coerce")
        work[c] = v.mask(v < 0)
    work = add_state_columns(work, "State_Abbr")
    grouped = work.groupby("state", dropna=True)
    out = grouped[items].sum(min_count=1)
    out.columns = [ITEM_MAP[c] for c in out.columns]
    out["n_jurisdictions"] = grouped.size()
    out["n_jurisdictions_missing_ballots"] = grouped["F1a"].apply(lambda s: int(s.isna().sum()))
    out = out.reset_index()
    out = add_state_columns(out, "state")
    out["year"] = year
    election = pd.Timestamp(general_election_date(year))
    out["observation_date"] = election
    out["period_start"] = election
    out["period_end"] = election
    return out


class EavsConnector(Connector):
    dataset_id = "eac-eavs"
    parser_version = "1"

    def _years(self, ctx: IngestContext) -> list[int]:
        years = ctx.option("years")
        if not years:
            return sorted(EAVS_FILES)
        if isinstance(years, str):
            years = [int(y) for y in years.split(",") if y.strip()]
        unknown = [y for y in years if y not in EAVS_FILES]
        if unknown:
            raise SchemaChangeError(f"no EAVS download URL registered for years {unknown}; known: {sorted(EAVS_FILES)}")
        return sorted(int(y) for y in years)

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        artifacts = []
        for year in self._years(ctx):
            url = EAVS_FILES[year]
            art = ctx.download(url, f"eavs_{year}.zip", note=f"EAVS {year} public release (nolabel CSV)")
            art.extra = {"year": year}
            artifacts.append(art)
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            year = art.extra.get("year") or int("".join(ch for ch in art.path.stem if ch.isdigit())[:4])
            raw = read_eavs_zip(art.path)
            out = normalize_eavs(raw, int(year))
            pub = release_calendar.from_url_month_folder(art.url or EAVS_FILES.get(int(year), ""))
            out["publication_date"] = pd.Timestamp(pub) if pub else pd.NaT
            out["publication_date_estimated"] = True
            out["source_url"] = art.url or EAVS_FILES.get(int(year))
            out["revision_vintage"] = _version_from_url(art.url or EAVS_FILES.get(int(year), ""))
            frames.append(out)
        return pd.concat(frames, ignore_index=True)


def _version_from_url(url: str) -> str | None:
    import re

    m = re.search(r"_V(\d+(?:\.\d+)?)", url)
    return f"V{m.group(1)}" if m else None
