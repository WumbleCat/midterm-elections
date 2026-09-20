"""Federal Election Commission bulk-file connectors (candidate master, financial summaries)."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

import pandas as pd

from ...exceptions import ParserError, SchemaChangeError
from ...geo import add_state_columns
from ...parties import normalize_party
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

BULK = "https://www.fec.gov/files/bulk-downloads/{cycle}/{name}{yy}.zip"

CN_COLUMNS = [
    "CAND_ID",
    "CAND_NAME",
    "CAND_PTY_AFFILIATION",
    "CAND_ELECTION_YR",
    "CAND_OFFICE_ST",
    "CAND_OFFICE",
    "CAND_OFFICE_DISTRICT",
    "CAND_ICI",
    "CAND_STATUS",
    "CAND_PCC",
    "CAND_ST1",
    "CAND_ST2",
    "CAND_CITY",
    "CAND_ST",
    "CAND_ZIP",
]

WEBALL_COLUMNS = [
    "CAND_ID",
    "CAND_NAME",
    "CAND_ICI",
    "PTY_CD",
    "CAND_PTY_AFFILIATION",
    "TTL_RECEIPTS",
    "TRANS_FROM_AUTH",
    "TTL_DISB",
    "TRANS_TO_AUTH",
    "COH_BOP",
    "COH_COP",
    "CAND_CONTRIB",
    "CAND_LOANS",
    "OTHER_LOANS",
    "CAND_LOAN_REPAY",
    "OTHER_LOAN_REPAY",
    "DEBTS_OWED_BY",
    "TTL_INDIV_CONTRIB",
    "CAND_OFFICE_ST",
    "CAND_OFFICE_DISTRICT",
    "SPEC_ELECTION",
    "PRIM_ELECTION",
    "RUN_ELECTION",
    "GEN_ELECTION",
    "GEN_ELECTION_PRECENT",
    "OTHER_POL_CMTE_CONTRIB",
    "POL_PTY_CONTRIB",
    "CVG_END_DT",
    "INDIV_REFUNDS",
    "CMTE_REFUNDS",
]

OFFICE_MAP = {"H": "house", "S": "senate", "P": "president"}


def bulk_url(cycle: int, name: str) -> str:
    return BULK.format(cycle=cycle, name=name, yy=f"{cycle % 100:02d}")


def read_pipe_zip(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not names:
                raise ParserError(f"{path.name}: no .txt inside zip")
            with zf.open(names[0]) as fh:
                df = pd.read_csv(
                    io.TextIOWrapper(fh, encoding="latin-1"),
                    sep="|",
                    header=None,
                    dtype=str,
                    keep_default_na=False,
                    na_values=[""],
                    quoting=3,
                )
    except zipfile.BadZipFile as exc:
        raise ParserError(f"{path.name}: not a zip file") from exc
    if df.shape[1] != len(columns):
        raise SchemaChangeError(
            f"{path.name}: expected {len(columns)} pipe-delimited fields, found {df.shape[1]}"
        )
    df.columns = columns
    return df


def _district(office: str, raw: str | None) -> str:
    if office != "house":
        return "statewide"
    if raw is None or str(raw).strip() in {"", "nan"}:
        return "statewide"
    try:
        n = int(raw)
    except ValueError:
        return str(raw)
    return "at-large" if n == 0 else f"{n:02d}"


def _office_from_id(cand_id: str) -> str | None:
    return OFFICE_MAP.get(str(cand_id)[:1].upper())


def normalize_candidate_master(
    df: pd.DataFrame, cycle: int, retrieval_date: dt.date
) -> pd.DataFrame:
    out = pd.DataFrame()
    out["candidate_id"] = df["CAND_ID"].str.strip()
    out["cycle"] = cycle
    out["election_year"] = pd.to_numeric(df["CAND_ELECTION_YR"], errors="coerce")
    out["name"] = df["CAND_NAME"].str.strip()
    out["party_raw"] = df["CAND_PTY_AFFILIATION"]
    out["party"] = df["CAND_PTY_AFFILIATION"].map(normalize_party)
    out["office"] = df["CAND_OFFICE"].str.strip().str.upper().map(OFFICE_MAP)
    st = df["CAND_OFFICE_ST"].str.strip().str.upper()
    tmp = add_state_columns(pd.DataFrame({"st": st}), "st")
    out["state"] = tmp["state"].where(out["office"] != "president", "US")
    out["state_fips"] = tmp["state_fips"]
    out["district_raw"] = df["CAND_OFFICE_DISTRICT"]
    out["district"] = [
        _district(o, d) for o, d in zip(out["office"], df["CAND_OFFICE_DISTRICT"], strict=True)
    ]
    out["incumbent_challenger_status"] = df["CAND_ICI"].str.strip().str.upper().replace({"": None})
    out["candidate_status"] = df["CAND_STATUS"].str.strip().str.upper().replace({"": None})
    out["principal_committee_id"] = df["CAND_PCC"].str.strip().replace({"": None})
    out = out[out["office"].notna() & out["candidate_id"].notna()]
    # The bulk file is a rolling snapshot. Candidate registrations (Form 2) are
    # public as filed and general-election candidates have filed well before the
    # primaries, so a row for cycle C is treated as available from mid-cycle
    # (June 30 of C) or the retrieval date, whichever is earlier. Flagged as
    # estimated; per-candidate first_file_date from the FEC API would be exact.
    out["observation_date"] = pd.Timestamp(retrieval_date)
    out["period_start"] = pd.Timestamp(cycle - 1, 1, 1)
    out["period_end"] = pd.Timestamp(cycle, 12, 31)
    out["publication_date"] = min(pd.Timestamp(retrieval_date), pd.Timestamp(cycle, 6, 30))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = retrieval_date.isoformat()
    return out.reset_index(drop=True)


_MONEY = {
    "TTL_RECEIPTS": "total_receipts",
    "TRANS_FROM_AUTH": "transfers_from_authorized",
    "TTL_DISB": "total_disbursements",
    "TRANS_TO_AUTH": "transfers_to_authorized",
    "COH_BOP": "cash_on_hand_beginning",
    "COH_COP": "cash_on_hand_end",
    "CAND_CONTRIB": "candidate_contributions",
    "CAND_LOANS": "candidate_loans",
    "OTHER_LOANS": "other_loans",
    "CAND_LOAN_REPAY": "candidate_loan_repayments",
    "OTHER_LOAN_REPAY": "other_loan_repayments",
    "DEBTS_OWED_BY": "debts_owed_by",
    "TTL_INDIV_CONTRIB": "individual_contributions",
    "OTHER_POL_CMTE_CONTRIB": "other_committee_contributions",
    "POL_PTY_CONTRIB": "party_contributions",
    "INDIV_REFUNDS": "refunds_individual",
    "CMTE_REFUNDS": "refunds_committee",
}


def normalize_candidate_finance(
    df: pd.DataFrame, cycle: int, retrieval_date: dt.date
) -> pd.DataFrame:
    out = pd.DataFrame()
    out["candidate_id"] = df["CAND_ID"].str.strip()
    out["cycle"] = cycle
    out["name"] = df["CAND_NAME"].str.strip()
    out["party_raw"] = df["CAND_PTY_AFFILIATION"]
    out["party"] = df["CAND_PTY_AFFILIATION"].map(normalize_party)
    out["office"] = out["candidate_id"].map(_office_from_id)
    st = df["CAND_OFFICE_ST"].str.strip().str.upper()
    tmp = add_state_columns(pd.DataFrame({"st": st}), "st")
    out["state"] = tmp["state"].where(out["office"] != "president", "US")
    out["state_fips"] = tmp["state_fips"]
    out["district"] = [
        _district(o, d) for o, d in zip(out["office"], df["CAND_OFFICE_DISTRICT"], strict=True)
    ]
    out["incumbent_challenger_status"] = df["CAND_ICI"].str.strip().str.upper().replace({"": None})
    out["coverage_end_date"] = pd.to_datetime(df["CVG_END_DT"], format="%m/%d/%Y", errors="coerce")
    for src, dst in _MONEY.items():
        out[dst] = pd.to_numeric(df[src], errors="coerce")
    out = out[out["coverage_end_date"].notna() & out["candidate_id"].notna()]
    out["observation_date"] = out["coverage_end_date"]
    out["period_start"] = pd.Timestamp(cycle - 1, 1, 1)
    out["period_end"] = out["coverage_end_date"]
    # Reports are due ~15-30 days after coverage end; the file we hold is a snapshot at retrieval.
    est = out["coverage_end_date"].map(
        lambda d: pd.Timestamp(release_calendar.fec_summary(d.date()))
    )
    out["publication_date"] = est.clip(upper=pd.Timestamp(retrieval_date))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = retrieval_date.isoformat()
    return out.reset_index(drop=True)


class _FecBulkConnector(Connector):
    file_name: str
    columns: list[str]

    def _cycles(self, ctx: IngestContext) -> list[int]:
        cycles = ctx.option("cycles")
        if cycles:
            if isinstance(cycles, str):
                cycles = [int(c) for c in cycles.split(",") if c.strip()]
            return sorted(int(c) for c in cycles)
        this_year = dt.date.today().year
        latest = this_year if this_year % 2 == 0 else this_year + 1
        return list(range(2010, latest + 1, 2))

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        artifacts = []
        for cycle in self._cycles(ctx):
            art = ctx.download(
                bulk_url(cycle, self.file_name),
                f"{self.file_name}{cycle}.zip",
                note=f"FEC {self.file_name} {cycle}",
            )
            art.extra = {"cycle": cycle}
            artifacts.append(art)
        return artifacts

    def _cycle_of(self, art: RawArtifact) -> int:
        return int(art.extra.get("cycle") or art.path.stem[len(self.file_name) :])


class CandidateMasterConnector(_FecBulkConnector):
    dataset_id = "fec-candidate-master"
    file_name = "cn"
    columns = CN_COLUMNS

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            cycle = self._cycle_of(art)
            frame = normalize_candidate_master(
                read_pipe_zip(art.path, CN_COLUMNS), cycle, ctx.retrieval_date
            )
            frame["source_url"] = art.url or bulk_url(cycle, "cn")
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)


class CandidateFinanceConnector(_FecBulkConnector):
    dataset_id = "fec-candidate-finance"
    file_name = "weball"
    columns = WEBALL_COLUMNS

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            cycle = self._cycle_of(art)
            frame = normalize_candidate_finance(
                read_pipe_zip(art.path, WEBALL_COLUMNS), cycle, ctx.retrieval_date
            )
            frame["source_url"] = art.url or bulk_url(cycle, "weball")
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)
