"""Bureau of Labor Statistics connectors.

* LAUS, CPI and CES/CPS national series come from the BLS Public Data API
  (v2 when ``BLS_API_KEY`` is set, otherwise the keyless v1 endpoint with its
  25-series / 10-year / 25-queries-per-day limits).
* QCEW annual averages come from the QCEW open-data CSV slices.

The API only returns the *current* vintage of every series, so
``publication_date`` is estimated from the BLS release calendar and flagged.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable

import pandas as pd

from ...dates import bls_period_to_date
from ...exceptions import DatasetUnavailableError, HTTPError, ParserError, SchemaChangeError
from ...geo import FIFTY_STATES_DC, STATE_BY_ABBR, add_state_columns
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

BLS_API_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_API_V2 = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _year_windows(start: int, end: int, span: int) -> Iterable[tuple[int, int]]:
    y = start
    while y <= end:
        yield y, min(y + span - 1, end)
        y += span


class _BlsApiConnector(Connector):
    """Shared fetch/parse for BLS API series."""

    default_start_year: int = 1996

    def series_ids(self, ctx: IngestContext) -> list[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def _limits(self, ctx: IngestContext) -> tuple[str, int, int, str | None]:
        key = ctx.settings.key_for("BLS_API_KEY")
        if key:
            return BLS_API_V2, 50, 20, key
        return BLS_API_V1, 25, 10, None

    def _years(self, ctx: IngestContext, span: int) -> tuple[int, int]:
        end = int(ctx.option("end_year", dt.date.today().year))
        default_start = self.default_start_year
        start = int(ctx.option("start_year", default_start))
        return start, end

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        url, max_series, span, key = self._limits(ctx)
        start, end = self._years(ctx, span)
        ids = self.series_ids(ctx)
        artifacts = []
        n = 0
        for y0, y1 in _year_windows(start, end, span):
            for chunk in _chunks(ids, max_series):
                payload: dict = {"seriesid": chunk, "startyear": str(y0), "endyear": str(y1)}
                if key:
                    payload["registrationkey"] = key
                resp = ctx.http.post_json(url, payload, headers={"Content-Type": "application/json"})
                body = resp.json()
                status = body.get("status")
                if status != "REQUEST_SUCCEEDED":
                    msg = "; ".join(body.get("message", [])) or status
                    raise HTTPError(f"BLS API request not processed: {msg}", status_code=resp.status_code, url=url)
                missing = [m for m in body.get("message", []) if "does not exist" in m]
                if missing:
                    raise SchemaChangeError(f"BLS reports unknown series ids: {missing[:3]}")
                for m in body.get("message", []):
                    ctx.note(f"BLS message: {m}")
                art = ctx.write_bytes(
                    json.dumps(body).encode(),
                    f"bls_{y0}_{y1}_part{n}.json",
                    url=url,
                    params={"seriesid": ",".join(chunk), "startyear": y0, "endyear": y1, "registrationkey": key},
                    http_status=resp.status_code,
                    note=f"BLS API {y0}-{y1} chunk {n}",
                )
                artifacts.append(art)
                n += 1
        return artifacts

    @staticmethod
    def read_series(artifacts: list[RawArtifact]) -> pd.DataFrame:
        rows = []
        for art in artifacts:
            if art.path.suffix != ".json":
                continue
            body = json.loads(art.path.read_text(encoding="utf-8"))
            for series in body.get("Results", {}).get("series", []):
                sid = series.get("seriesID")
                for obs in series.get("data", []):
                    rows.append(
                        {
                            "series_id": sid,
                            "year": int(obs["year"]),
                            "period": obs["period"],
                            "value": obs["value"],
                            "footnotes": ";".join(f.get("text", "") for f in obs.get("footnotes", []) if f),
                            "source_url": art.url,
                        }
                    )
        if not rows:
            raise ParserError("BLS artifacts contained no series data")
        df = pd.DataFrame(rows)
        df["date"] = [bls_period_to_date(y, p) for y, p in zip(df["year"], df["period"], strict=True)]
        df = df[df["date"].notna()].copy()
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"].replace("-", None), errors="coerce")
        return df.drop(columns=["year", "period"])


# ----------------------------------------------------------------- LAUS

LAUS_MEASURES = {"03": "unemployment_rate", "04": "unemployment", "05": "employment", "06": "labor_force"}


def laus_series_id(state_fips: str, measure_code: str, seasonally_adjusted: bool = True) -> str:
    prefix = "LASST" if seasonally_adjusted else "LAUST"
    # e.g. LASST420000000000003 = LAS + ST42 + 00000000000 + 03 (20 characters)
    return f"{prefix}{state_fips}{'0' * 11}{measure_code}"


def parse_laus_series_id(sid: str) -> tuple[str, str, bool] | None:
    if len(sid) != 20 or not sid.startswith(("LASST", "LAUST")):
        return None
    return sid[5:7], sid[-2:], sid.startswith("LASST")


def normalize_laus(series: pd.DataFrame) -> pd.DataFrame:
    parsed = series["series_id"].map(parse_laus_series_id)
    bad = parsed.isna()
    if bad.any():
        raise SchemaChangeError(f"unexpected LAUS series ids: {series.loc[bad, 'series_id'].unique()[:5]}")
    series = series.copy()
    series["state_fips_raw"] = parsed.map(lambda t: t[0])
    series["measure"] = parsed.map(lambda t: LAUS_MEASURES.get(t[1]))
    series["seasonally_adjusted"] = parsed.map(lambda t: t[2])
    series = add_state_columns(series, "state_fips_raw")
    wide = series.pivot_table(
        index=["state", "state_fips", "state_name", "date", "seasonally_adjusted"],
        columns="measure",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    for m in LAUS_MEASURES.values():
        if m not in wide.columns:
            wide[m] = pd.NA
    wide["observation_date"] = wide["date"]
    wide["period_start"] = wide["date"]
    wide["period_end"] = wide["date"].map(lambda d: pd.Timestamp(release_calendar.month_end(d.date())))
    wide["publication_date"] = wide["date"].map(lambda d: pd.Timestamp(release_calendar.bls_laus_state(d.date())))
    wide["publication_date_estimated"] = True
    return wide


LAUS_BULK_URL = "https://download.bls.gov/pub/time.series/la/la.data.3.AllStatesS"


def read_laus_flat_file(path) -> pd.DataFrame:  # noqa: ANN001
    """Parse a BLS time-series flat file (tab-delimited, padded fields) into series rows."""
    df = pd.read_csv(path, sep="	", dtype=str, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    need = {"series_id", "year", "period", "value"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"LAUS flat file missing {sorted(need - set(df.columns))}")
    df["series_id"] = df["series_id"].str.strip()
    df = df[df["period"].str.startswith("M") & (df["period"] != "M13")].copy()
    df["date"] = [bls_period_to_date(y, p) for y, p in zip(df["year"], df["period"], strict=True)]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"].str.strip().replace("-", None), errors="coerce")
    df["source_url"] = LAUS_BULK_URL
    return df[["series_id", "date", "value", "source_url"]]


class LausConnector(_BlsApiConnector):
    """State LAUS via the official bulk flat file (default when a contact email is
    configured, as BLS requires an identifying User-Agent) or the API (``mode=api``)."""

    dataset_id = "bls-laus"

    def _mode(self, ctx: IngestContext) -> str:
        mode = str(ctx.option("mode", "auto")).lower()
        if mode == "auto":
            mode = "bulk" if ctx.settings.contact_email else "api"
        if mode == "bulk" and not ctx.settings.contact_email:
            raise DatasetUnavailableError(
                "BLS bulk downloads require ELECTIONDATA_CONTACT_EMAIL (sent in the User-Agent); set it or use mode=api"
            )
        return mode

    def _years(self, ctx: IngestContext, span: int) -> tuple[int, int]:
        end = int(ctx.option("end_year", dt.date.today().year))
        start = int(ctx.option("start_year", end - span + 1))
        return start, end

    def series_ids(self, ctx: IngestContext) -> list[str]:
        return [laus_series_id(STATE_BY_ABBR[s].fips, code) for s in FIFTY_STATES_DC for code in LAUS_MEASURES]

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        if self._mode(ctx) == "api":
            return super().fetch(ctx)
        art = ctx.download(LAUS_BULK_URL, "la.data.3.AllStatesS.tsv", note="LAUS all states, seasonally adjusted (bulk)")
        return [art]

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        flat = [a for a in artifacts if a.path.suffix == ".tsv"]
        if flat:
            series = read_laus_flat_file(flat[0].path)
            wanted = set(self.series_ids(ctx))
            series = series[series["series_id"].isin(wanted)]
            start_year = ctx.option("start_year")
            if start_year:
                series = series[series["date"].dt.year >= int(start_year)]
        else:
            series = self.read_series(artifacts)
        out = normalize_laus(series)
        out["revision_vintage"] = ctx.retrieval_date.isoformat()
        out["source_url"] = artifacts[0].url if artifacts else BLS_API_V1
        return out


# ------------------------------------------------------- national series

NATIONAL_SERIES: dict[str, tuple[str, bool, str]] = {
    # series_id: (measure, seasonally_adjusted, unit)
    "CUUR0000SA0": ("cpi_all_items", False, "index 1982-84=100"),
    "CUSR0000SA0": ("cpi_all_items", True, "index 1982-84=100"),
    "CUUR0000SA0L1E": ("cpi_core", False, "index 1982-84=100"),
    "CUSR0000SA0L1E": ("cpi_core", True, "index 1982-84=100"),
    "CES0000000001": ("nonfarm_payrolls", True, "thousands"),
    "CES0500000003": ("average_hourly_earnings", True, "USD"),
    "LNS14000000": ("unemployment_rate", True, "percent"),
    "LNS11300000": ("labor_force_participation_rate", True, "percent"),
}


def normalize_national(series: pd.DataFrame, rule) -> pd.DataFrame:  # noqa: ANN001
    unknown = set(series["series_id"]) - set(NATIONAL_SERIES)
    if unknown:
        raise SchemaChangeError(f"unexpected national series ids: {sorted(unknown)[:5]}")
    out = series.copy()
    out["measure"] = out["series_id"].map(lambda s: NATIONAL_SERIES[s][0])
    out["seasonally_adjusted"] = out["series_id"].map(lambda s: NATIONAL_SERIES[s][1])
    out["unit"] = out["series_id"].map(lambda s: NATIONAL_SERIES[s][2])
    out["observation_date"] = out["date"]
    out["period_start"] = out["date"]
    out["period_end"] = out["date"].map(lambda d: pd.Timestamp(release_calendar.month_end(d.date())))
    out["publication_date"] = out["date"].map(lambda d: pd.Timestamp(rule(d.date())))
    out["publication_date_estimated"] = True
    return out[["date", "series_id", "measure", "value", "seasonally_adjusted", "unit", "observation_date", "period_start", "period_end", "publication_date", "publication_date_estimated", "source_url"]]


class CpiConnector(_BlsApiConnector):
    dataset_id = "bls-cpi"

    def series_ids(self, ctx: IngestContext) -> list[str]:
        return [s for s in NATIONAL_SERIES if s.startswith("CU")]

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        out = normalize_national(self.read_series(artifacts), release_calendar.bls_cpi)
        out["revision_vintage"] = ctx.retrieval_date.isoformat()
        return out


class CesNationalConnector(_BlsApiConnector):
    dataset_id = "bls-ces-national"

    def series_ids(self, ctx: IngestContext) -> list[str]:
        return [s for s in NATIONAL_SERIES if s.startswith(("CES", "LNS"))]

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        out = normalize_national(self.read_series(artifacts), release_calendar.bls_employment_situation)
        out["revision_vintage"] = ctx.retrieval_date.isoformat()
        return out


# ----------------------------------------------------------------- QCEW

QCEW_AREA_URL = "https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv"
QCEW_STATE_AGGLVL = {"50", "51", "53", "54"}  # state total; by ownership; supersector; NAICS sector


def qcew_area_url(year: int, state_fips: str) -> str:
    return QCEW_AREA_URL.format(year=year, area=f"{state_fips}000")


def normalize_qcew(df: pd.DataFrame, year: int) -> pd.DataFrame:
    need = {"area_fips", "own_code", "industry_code", "agglvl_code", "annual_avg_emplvl", "total_annual_wages"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"QCEW file missing {sorted(need - set(df.columns))}")
    sub = df[df["agglvl_code"].isin(QCEW_STATE_AGGLVL)].copy()
    sub["state_fips_raw"] = sub["area_fips"].str[:2]
    sub = add_state_columns(sub, "state_fips_raw")
    out = pd.DataFrame(
        {
            "state": sub["state"],
            "state_fips": sub["state_fips"],
            "state_name": sub["state_name"],
            "year": year,
            "industry_code": sub["industry_code"].astype(str),
            "own_code": sub["own_code"].astype(str),
            "agglvl_code": sub["agglvl_code"].astype(str),
            "annual_avg_establishments": pd.to_numeric(sub["annual_avg_estabs"], errors="coerce"),
            "annual_avg_employment": pd.to_numeric(sub["annual_avg_emplvl"], errors="coerce"),
            "total_annual_wages": pd.to_numeric(sub["total_annual_wages"], errors="coerce"),
            "annual_avg_weekly_wage": pd.to_numeric(sub["annual_avg_wkly_wage"], errors="coerce"),
            "avg_annual_pay": pd.to_numeric(sub["avg_annual_pay"], errors="coerce"),
        }
    )
    if "disclosure_code" in sub.columns:
        suppressed = sub["disclosure_code"].astype(str).str.strip().eq("N")
        for c in ("annual_avg_establishments", "annual_avg_employment", "total_annual_wages", "annual_avg_weekly_wage", "avg_annual_pay"):
            out.loc[suppressed.values, c] = pd.NA
    out["observation_date"] = pd.Timestamp(year, 12, 31)
    out["period_start"] = pd.Timestamp(year, 1, 1)
    out["period_end"] = pd.Timestamp(year, 12, 31)
    out["publication_date"] = pd.Timestamp(release_calendar.bls_qcew_annual(year))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = str(year)
    return out.reset_index(drop=True)


class QcewConnector(Connector):
    dataset_id = "bls-qcew"

    def _years(self, ctx: IngestContext) -> list[int]:
        years = ctx.option("years")
        if years:
            if isinstance(years, str):
                years = [int(y) for y in years.split(",") if y.strip()]
            return sorted(int(y) for y in years)
        this_year = dt.date.today().year
        return [this_year - 2, this_year - 1]

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        artifacts = []
        for year in self._years(ctx):
            for st in FIFTY_STATES_DC:
                fips = STATE_BY_ABBR[st].fips
                try:
                    art = ctx.download(qcew_area_url(year, fips), f"qcew_{year}_{fips}.csv", note=f"QCEW annual {year} {st}")
                except DatasetUnavailableError:
                    ctx.note(f"QCEW {year} not yet available for {st}; skipping year")
                    break
                art.extra = {"year": year, "state": st}
                artifacts.append(art)
        if not artifacts:
            raise DatasetUnavailableError("no QCEW annual files available for the requested years")
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            year = art.extra.get("year") or int(art.path.stem.split("_")[1])
            raw = pd.read_csv(art.path, dtype=str)
            frame = normalize_qcew(raw, int(year))
            frame["source_url"] = art.url
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)
