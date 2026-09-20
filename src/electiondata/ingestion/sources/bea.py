"""Bureau of Economic Analysis Regional API connectors (require BEA_API_KEY).

Request shape (verified against the public API documentation):
    https://apps.bea.gov/api/data/?UserID=KEY&method=GetData&datasetname=Regional
        &TableName=SAGDP9N&LineCode=1&GeoFips=STATE&Year=ALL&ResultFormat=JSON
Response: {"BEAAPI": {"Results": {"Data": [{"GeoFips": "42000", "GeoName": ..,
    "TimePeriod": "2023", "CL_UNIT": .., "UNIT_MULT": "6", "DataValue": "1,234"}]}}}
"""

from __future__ import annotations

import json

import pandas as pd

from ...exceptions import HTTPError, ParserError, SchemaChangeError
from ...geo import add_state_columns
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

BEA_URL = "https://apps.bea.gov/api/data/"


def bea_params(key: str, table: str, line_code: str, year: str = "ALL") -> dict[str, str]:
    return {
        "UserID": key,
        "method": "GetData",
        "datasetname": "Regional",
        "TableName": table,
        "LineCode": line_code,
        "GeoFips": "STATE",
        "Year": year,
        "ResultFormat": "JSON",
    }


def parse_bea_payload(payload: dict) -> pd.DataFrame:
    api = payload.get("BEAAPI", {})
    results = api.get("Results", {})
    if "Error" in results or "Error" in api:
        err = results.get("Error") or api.get("Error")
        raise HTTPError(f"BEA API error: {err}")
    data = results.get("Data")
    if data is None:
        raise ParserError(f"BEA payload without Data: {str(payload)[:200]}")
    df = pd.DataFrame(data)
    need = {"GeoFips", "TimePeriod", "DataValue"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"BEA payload missing {sorted(need - set(df.columns))}")
    return df


def normalize_bea(
    df: pd.DataFrame, measure: str, table: str, line_code: str, pub_rule
) -> pd.DataFrame:  # noqa: ANN001
    work = df.copy()
    work["state_fips_raw"] = work["GeoFips"].astype(str).str[:2]
    work = add_state_columns(work, "state_fips_raw")
    work = work[work["state"].notna()]
    value = pd.to_numeric(
        work["DataValue"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    year = pd.to_numeric(work["TimePeriod"].astype(str).str[:4], errors="coerce").astype("Int64")
    out = pd.DataFrame(
        {
            "state": work["state"],
            "state_fips": work["state_fips"],
            "state_name": work["state_name"],
            "year": year,
            "measure": measure,
            "value": value,
            "unit": work["CL_UNIT"] if "CL_UNIT" in work.columns else None,
            "bea_table": table,
            "line_code": str(line_code),
        }
    )
    out = out[out["year"].notna()]
    out["observation_date"] = out["year"].map(lambda y: pd.Timestamp(int(y), 12, 31))
    out["period_start"] = out["year"].map(lambda y: pd.Timestamp(int(y), 1, 1))
    out["period_end"] = out["observation_date"]
    out["publication_date"] = out["year"].map(lambda y: pd.Timestamp(pub_rule(int(y))))
    out["publication_date_estimated"] = True
    return out.reset_index(drop=True)


class _BeaConnector(Connector):
    # (measure, table, line_code)
    requests: tuple[tuple[str, str, str], ...]
    pub_rule = staticmethod(release_calendar.bea_annual)

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        key = ctx.require_key("BEA_API_KEY")
        artifacts = []
        for measure, table, line in self.requests:
            params = bea_params(key, table, line)
            resp = ctx.http.get(BEA_URL, params=params)
            art = ctx.write_bytes(
                resp.content,
                f"bea_{table}_{line}.json",
                url=BEA_URL,
                params=params,
                http_status=resp.status_code,
                note=f"BEA {table} line {line} ({measure})",
            )
            art.extra = {"measure": measure, "table": table, "line_code": line}
            artifacts.append(art)
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        lookup = {(table_, line_): m for m, table_, line_ in self.requests}
        frames = []
        for art in artifacts:
            if art.path.suffix != ".json":
                continue
            table = art.extra.get("table") or art.path.stem.split("_")[1]
            line = art.extra.get("line_code") or art.path.stem.split("_")[2]
            measure = art.extra.get("measure") or lookup[(table, line)]
            payload = json.loads(art.path.read_text(encoding="utf-8"))
            frame = normalize_bea(parse_bea_payload(payload), measure, table, line, self.pub_rule)
            frame["source_url"] = BEA_URL
            frame["revision_vintage"] = ctx.retrieval_date.isoformat()
            frames.append(frame)
        if not frames:
            raise ParserError("no BEA artifacts")
        return pd.concat(frames, ignore_index=True)


class StateGdpConnector(_BeaConnector):
    dataset_id = "bea-state-gdp"
    requests = (
        ("real_gdp", "SAGDP9N", "1"),
        ("nominal_gdp", "SAGDP2N", "1"),
    )


class PersonalIncomeConnector(_BeaConnector):
    dataset_id = "bea-personal-income"
    requests = (
        ("personal_income", "SAINC1", "1"),
        ("population", "SAINC1", "2"),
        ("per_capita_personal_income", "SAINC1", "3"),
    )


class RppConnector(_BeaConnector):
    dataset_id = "bea-rpp"
    pub_rule = staticmethod(release_calendar.bea_rpp)
    requests = (
        ("regional_price_parity", "SARPP", "1"),
        ("real_personal_income", "SARPI", "1"),
        ("real_per_capita_personal_income", "SARPI", "2"),
    )
