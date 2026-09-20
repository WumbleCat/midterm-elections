"""U.S. Census Bureau connectors: PEP population, Gazetteer, urban/rural, ACS."""

from __future__ import annotations

import datetime as dt
import json
import zipfile
from pathlib import Path

import pandas as pd

from ...exceptions import ParserError, SchemaChangeError
from ...geo import FIFTY_STATES_DC, add_state_columns
from ...quality import release_calendar
from ..base import Connector, IngestContext, RawArtifact

# ------------------------------------------------------------------ PEP

_PEP = "https://www2.census.gov/programs-surveys/popest/datasets"
PEP_FILES: dict[int, str] = {
    # vintage -> URL (all verified reachable 2026-09-20). Vintages 2011-2014 are not
    # published as alldata CSVs at these paths; their years are covered by later vintages.
    2024: f"{_PEP}/2020-2024/state/totals/NST-EST2024-ALLDATA.csv",
    2023: f"{_PEP}/2020-2023/state/totals/NST-EST2023-ALLDATA.csv",
    2022: f"{_PEP}/2020-2022/state/totals/NST-EST2022-ALLDATA.csv",
    2021: f"{_PEP}/2020-2021/state/totals/NST-EST2021-alldata.csv",
    2019: f"{_PEP}/2010-2019/national/totals/nst-est2019-alldata.csv",
    2018: f"{_PEP}/2010-2018/national/totals/nst-est2018-alldata.csv",
    2017: f"{_PEP}/2010-2017/national/totals/nst-est2017-alldata.csv",
    2016: f"{_PEP}/2010-2016/national/totals/nst-est2016-alldata.csv",
    2015: f"{_PEP}/2010-2015/national/totals/nst-est2015-alldata.csv",
    2009: f"{_PEP}/2000-2010/intercensal/state/st-est00int-alldata.csv",
}

_PEP_MEASURES = {
    "POPESTIMATE": "population",
    "BIRTHS": "births",
    "DEATHS": "deaths",
    "NATURALCHG": "natural_change",
    "NATURALINC": "natural_change",
    "INTERNATIONALMIG": "international_migration",
    "DOMESTICMIG": "domestic_migration",
    "NETMIG": "net_migration",
    "RDOMESTICMIG": "domestic_migration_rate",
    "RNETMIG": "net_migration_rate",
}


def read_pep_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype=str, encoding="latin-1")
    except Exception as exc:  # noqa: BLE001
        raise ParserError(f"cannot read PEP file {path.name}: {exc}") from exc


def normalize_pep(df: pd.DataFrame, vintage: int) -> pd.DataFrame:
    """Wide NST-EST layout -> long-by-year rows with population and components."""
    if "STATE" not in df.columns or "NAME" not in df.columns:
        raise SchemaChangeError("PEP file missing STATE/NAME columns")
    if "SUMLEV" in df.columns:
        states = df[df["SUMLEV"] == "040"].copy()
    else:  # intercensal layout: total rows have SEX/ORIGIN/RACE/AGEGRP == 0
        states = df[
            (df.get("SEX", "0") == "0")
            & (df.get("ORIGIN", "0") == "0")
            & (df.get("RACE", "0") == "0")
            & (df.get("AGEGRP", "0") == "0")
            & (df["STATE"] != "0")
            & (df["STATE"] != "00")
        ].copy()
    states = add_state_columns(states, "STATE")
    states = states[states["state"].notna()]
    records = []
    for prefix, measure in _PEP_MEASURES.items():
        cols = [c for c in states.columns if c.startswith(prefix) and c[len(prefix) :].isdigit()]
        for c in cols:
            year = int(c[len(prefix) :])
            if measure == "population" and year == 2010 and vintage == 2009:
                continue  # intercensal file's 2010 column duplicates the 2010-2019 vintage
            sub = states[["state", "state_fips", "state_name", c]].rename(columns={c: "value"})
            sub["year"] = year
            sub["measure"] = measure
            records.append(sub)
    long = pd.concat(records, ignore_index=True)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    wide = long.pivot_table(
        index=["state", "state_fips", "state_name", "year"],
        columns="measure",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    wide["revision_vintage"] = str(vintage)
    wide["observation_date"] = wide["year"].map(lambda y: pd.Timestamp(int(y), 7, 1))
    wide["period_start"] = wide["year"].map(lambda y: pd.Timestamp(int(y), 7, 1))
    wide["period_end"] = wide["year"].map(lambda y: pd.Timestamp(int(y), 7, 1))
    wide["publication_date"] = pd.Timestamp(release_calendar.pep_vintage(vintage))
    wide["publication_date_estimated"] = True
    return wide[wide["state"].isin(FIFTY_STATES_DC + ("PR",))].reset_index(drop=True)


class PepPopulationConnector(Connector):
    dataset_id = "census-pep-population"

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        out = []
        for vintage, url in sorted(PEP_FILES.items()):
            art = ctx.download(
                url, f"pep_vintage_{vintage}.csv", note=f"PEP state totals vintage {vintage}"
            )
            art.extra = {"vintage": vintage}
            out.append(art)
        return out

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            vintage = art.extra.get("vintage") or int(art.path.stem.rsplit("_", 1)[-1])
            frame = normalize_pep(read_pep_csv(art.path), int(vintage))
            frame["source_url"] = art.url or PEP_FILES.get(int(vintage))
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------ Gazetteer


GAZETTEER_DEFAULT_VINTAGES = (2012, 2016, 2020, 2024)


def gazetteer_url(vintage: int) -> str:
    """State file for 2024+; earlier vintages only publish county files (summed to states)."""
    base = f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{vintage}_Gazetteer"
    if vintage >= 2024:
        return f"{base}/{vintage}_Gaz_state_national.zip"
    return f"{base}/{vintage}_Gaz_counties_national.zip"


def normalize_gazetteer(df: pd.DataFrame, vintage: int) -> pd.DataFrame:
    df = df.rename(columns=lambda c: c.strip())
    need = {"USPS", "ALAND_SQMI", "AWATER_SQMI"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"Gazetteer file missing {sorted(need - set(df.columns))}")
    work = df[["USPS", "ALAND_SQMI", "AWATER_SQMI"]].copy()
    work["ALAND_SQMI"] = pd.to_numeric(work["ALAND_SQMI"], errors="coerce")
    work["AWATER_SQMI"] = pd.to_numeric(work["AWATER_SQMI"], errors="coerce")
    work = add_state_columns(work, "USPS")
    work = work[work["state"].notna()]
    # county files -> sum to state; state files have one row per state already
    agg = work.groupby(["state", "state_fips", "state_name"], as_index=False)[
        ["ALAND_SQMI", "AWATER_SQMI"]
    ].sum(min_count=1)
    out = pd.DataFrame(
        {
            "state": agg["state"],
            "state_fips": agg["state_fips"],
            "state_name": agg["state_name"],
            "year": vintage,
            "land_area_sq_miles": agg["ALAND_SQMI"],
            "water_area_sq_miles": agg["AWATER_SQMI"],
        }
    )
    out["observation_date"] = pd.Timestamp(vintage, 1, 1)
    out["period_start"] = pd.Timestamp(vintage, 1, 1)
    out["period_end"] = pd.Timestamp(vintage, 12, 31)
    out["publication_date"] = pd.Timestamp(release_calendar.census_geography(vintage))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = str(vintage)
    return out.reset_index(drop=True)


class GazetteerConnector(Connector):
    dataset_id = "census-gazetteer"

    def _vintages(self, ctx: IngestContext) -> list[int]:
        v = ctx.option("vintages") or ctx.option("vintage")
        if not v:
            return list(GAZETTEER_DEFAULT_VINTAGES)
        if isinstance(v, str):
            return sorted(int(x) for x in v.split(",") if x.strip())
        return sorted(int(x) for x in (v if isinstance(v, list | tuple) else [v]))

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        artifacts = []
        for vintage in self._vintages(ctx):
            art = ctx.download(
                gazetteer_url(vintage), f"gazetteer_{vintage}.zip", note=f"Gazetteer {vintage}"
            )
            art.extra = {"vintage": vintage}
            artifacts.append(art)
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        frames = []
        for art in artifacts:
            vintage = art.extra.get("vintage") or int(art.path.stem.rsplit("_", 1)[-1])
            with zipfile.ZipFile(art.path) as zf:
                name = next(n for n in zf.namelist() if n.endswith(".txt"))
                raw = pd.read_csv(zf.open(name), sep="	", dtype=str, encoding="latin-1")
            frame = normalize_gazetteer(raw, int(vintage))
            frame["source_url"] = art.url or gazetteer_url(int(vintage))
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------- urban/rural

URBAN_RURAL_COUNTY_2020 = "https://www2.census.gov/geo/docs/reference/ua/2020_UA_COUNTY.xlsx"


def normalize_urban_rural_county(df: pd.DataFrame, census_year: int = 2020) -> pd.DataFrame:
    need = {"STATE", "POP_COU", "POP_URB", "POP_RUR"}
    if not need <= set(df.columns):
        raise SchemaChangeError(f"urban/rural county file missing {sorted(need - set(df.columns))}")
    work = df[["STATE", "POP_COU", "POP_URB", "POP_RUR"]].copy()
    for c in ("POP_COU", "POP_URB", "POP_RUR"):
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = add_state_columns(work, "STATE")
    agg = work.groupby(["state", "state_fips", "state_name"], as_index=False)[
        ["POP_COU", "POP_URB", "POP_RUR"]
    ].sum(min_count=1)
    out = agg.rename(
        columns={
            "POP_COU": "total_population",
            "POP_URB": "urban_population",
            "POP_RUR": "rural_population",
        }
    )
    out["pct_urban"] = out["urban_population"] / out["total_population"]
    out["pct_rural"] = out["rural_population"] / out["total_population"]
    out["year"] = census_year
    out["observation_date"] = pd.Timestamp(census_year, 4, 1)
    out["period_start"] = pd.Timestamp(census_year, 4, 1)
    out["period_end"] = pd.Timestamp(census_year, 4, 1)
    out["publication_date"] = pd.Timestamp(release_calendar.urban_rural(census_year))
    out["publication_date_estimated"] = True
    out["revision_vintage"] = str(census_year)
    return out


class UrbanRuralConnector(Connector):
    dataset_id = "census-urban-rural"

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        art = ctx.download(
            URBAN_RURAL_COUNTY_2020, "2020_UA_COUNTY.xlsx", note="2020 urban/rural by county"
        )
        art.extra = {"census_year": 2020}
        return [art]

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        art = artifacts[0]
        raw = pd.read_excel(art.path, dtype=str)
        out = normalize_urban_rural_county(raw, int(art.extra.get("census_year", 2020)))
        out["source_url"] = art.url or URBAN_RURAL_COUNTY_2020
        return out


# ------------------------------------------------------------------ ACS

ACS_BASE = "https://api.census.gov/data"

# Detailed-table variables reduced to the demographics schema. Sums are over the listed ids.
_B01001_MALE_AGE = {
    "pct_under_18": ["003", "004", "005", "006"],
    "pct_18_24": ["007", "008", "009", "010"],
    "pct_25_34": ["011", "012"],
    "pct_35_44": ["013", "014"],
    "pct_45_54": ["015", "016"],
    "pct_55_64": ["017", "018", "019"],
    "pct_65_74": ["020", "021", "022"],
    "pct_75_plus": ["023", "024", "025"],
}


def _b01001(ids: list[str]) -> list[str]:
    male = [f"B01001_{i}E" for i in ids]
    female = [f"B01001_{int(i) + 24:03d}E" for i in ids]
    return male + female


ACS_VARIABLES: dict[str, list[str]] = {
    "total_population": ["B01003_001E"],
    "median_age": ["B01002_001E"],
    "_male": ["B01001_002E"],
    "_female": ["B01001_026E"],
    **{k: _b01001(v) for k, v in _B01001_MALE_AGE.items()},
    "_pop25": ["B15003_001E"],
    "pct_less_than_high_school": [f"B15003_{i:03d}E" for i in range(2, 17)],
    "pct_high_school": ["B15003_017E", "B15003_018E"],
    "pct_some_college": ["B15003_019E", "B15003_020E"],
    "pct_associate_degree": ["B15003_021E"],
    "pct_bachelors": ["B15003_022E"],
    "pct_graduate_degree": ["B15003_023E", "B15003_024E", "B15003_025E"],
    "median_household_income": ["B19013_001E"],
    "_agg_hh_income": ["B19025_001E"],
    "_households": ["B11001_001E"],
    "per_capita_income": ["B19301_001E"],
    "gini_coefficient": ["B19083_001E"],
    "_poverty_universe": ["B17001_001E"],
    "_poverty_below": ["B17001_002E"],
    "_white": ["B02001_002E"],
    "_white_nh": ["B03002_003E"],
    "_black_nh": ["B03002_004E"],
    "_aian_nh": ["B03002_005E"],
    "_asian_nh": ["B03002_006E"],
    "_nhpi_nh": ["B03002_007E"],
    "_other_nh": ["B03002_008E"],
    "_multi_nh": ["B03002_009E"],
    "_hispanic": ["B03002_012E"],
    "_nativity_total": ["B05002_001E"],
    "_native_born": ["B05002_002E"],
    "_foreign_born": ["B05002_013E"],
    "_naturalized": ["B05002_014E"],
    "_non_citizen": ["B05002_021E"],
    "citizen_voting_age_population": ["B05003_009E", "B05003_011E", "B05003_020E", "B05003_022E"],
}


def acs_variable_list() -> list[str]:
    seen: list[str] = []
    for ids in ACS_VARIABLES.values():
        for v in ids:
            if v not in seen:
                seen.append(v)
    return seen


def parse_acs_json(payload: list[list[str]]) -> pd.DataFrame:
    """Census API returns a header row followed by rows of strings."""
    if not payload or not isinstance(payload[0], list):
        raise ParserError("unexpected Census API payload")
    return pd.DataFrame(payload[1:], columns=payload[0])


def normalize_acs(frames: list[pd.DataFrame], year: int, survey: str) -> pd.DataFrame:
    """Merge chunked API responses (same states) and compute schema shares."""
    merged = frames[0]
    for f in frames[1:]:
        merged = merged.merge(f, on="state", suffixes=("", "_dup"))
    merged = merged.loc[:, ~merged.columns.str.endswith("_dup")]
    wide = add_state_columns(merged.rename(columns={"state": "state_code"}), "state_code")
    wide = wide[wide["state"].notna()]
    values = {}
    for name, ids in ACS_VARIABLES.items():
        present = [i for i in ids if i in wide.columns]
        if not present:
            values[name] = pd.Series(pd.NA, index=wide.index, dtype="Float64")
            continue
        block = wide[present].apply(pd.to_numeric, errors="coerce")
        # Census uses large negative sentinels (-666666666 etc.) for unavailable cells.
        block = block.mask(block < -1e6)
        values[name] = block.sum(axis=1, min_count=1) if len(present) > 1 else block.iloc[:, 0]
    v = pd.DataFrame(values)
    total = v["total_population"]
    out = pd.DataFrame(
        {
            "state": wide["state"],
            "state_fips": wide["state_fips"],
            "state_name": wide["state_name"],
            "year": year,
            "survey": survey,
            "total_population": total,
            "median_age": v["median_age"],
            "pct_male": v["_male"] / total,
            "pct_female": v["_female"] / total,
            "median_household_income": v["median_household_income"],
            "mean_household_income": v["_agg_hh_income"] / v["_households"],
            "per_capita_income": v["per_capita_income"],
            "gini_coefficient": v["gini_coefficient"],
            "poverty_rate": v["_poverty_below"] / v["_poverty_universe"],
            "pct_white": v["_white"] / total,
            "pct_white_non_hispanic": v["_white_nh"] / total,
            "pct_black": v["_black_nh"] / total,
            "pct_hispanic_latino": v["_hispanic"] / total,
            "pct_asian": v["_asian_nh"] / total,
            "pct_native_american": v["_aian_nh"] / total,
            "pct_native_hawaiian_pacific_islander": v["_nhpi_nh"] / total,
            "pct_multiracial": v["_multi_nh"] / total,
            "pct_other_race": v["_other_nh"] / total,
            "pct_foreign_born": v["_foreign_born"] / v["_nativity_total"],
            "pct_naturalized_citizen": v["_naturalized"] / v["_nativity_total"],
            "pct_non_citizen": v["_non_citizen"] / v["_nativity_total"],
            "pct_native_born": v["_native_born"] / v["_nativity_total"],
            "citizen_voting_age_population": v["citizen_voting_age_population"],
        }
    )
    for k in _B01001_MALE_AGE:
        out[k] = v[k] / total
    out["pct_65_plus"] = out["pct_65_74"] + out["pct_75_plus"]
    edu = [
        "pct_less_than_high_school",
        "pct_high_school",
        "pct_some_college",
        "pct_associate_degree",
        "pct_bachelors",
        "pct_graduate_degree",
    ]
    for k in edu:
        out[k] = v[k] / v["_pop25"]
    out["pct_bachelors_or_higher"] = out["pct_bachelors"] + out["pct_graduate_degree"]
    out["pct_high_school_or_higher"] = 1 - out["pct_less_than_high_school"]
    out["observation_date"] = pd.Timestamp(year, 12, 31)
    out["period_start"] = pd.Timestamp(year - (4 if survey == "acs5" else 0), 1, 1)
    out["period_end"] = pd.Timestamp(year, 12, 31)
    pub = release_calendar.acs_5year(year) if survey == "acs5" else release_calendar.acs_1year(year)
    out["publication_date"] = pd.Timestamp(pub)
    out["publication_date_estimated"] = True
    out["revision_vintage"] = f"{survey}-{year}"
    return out.reset_index(drop=True)


class AcsProfileConnector(Connector):
    """ACS 1-year (or 5-year) state profile from the Census API. Requires CENSUS_API_KEY."""

    dataset_id = "census-acs-profile"
    chunk_size = 45  # API limit is 50 variables per call (NAME included)

    def _years(self, ctx: IngestContext, survey: str) -> list[int]:
        years = ctx.option("years")
        if years:
            if isinstance(years, str):
                years = [int(y) for y in years.split(",") if y.strip()]
            return sorted(int(y) for y in years)
        latest = dt.date.today().year - 2
        ys = list(range(2010, latest + 1))
        if survey == "acs1":
            ys = [y for y in ys if y != 2020]  # no standard 2020 1-year release
        return ys

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        key = ctx.require_key("CENSUS_API_KEY")
        survey = str(ctx.option("survey", "acs1"))
        variables = acs_variable_list()
        chunks = [
            variables[i : i + self.chunk_size] for i in range(0, len(variables), self.chunk_size)
        ]
        artifacts = []
        for year in self._years(ctx, survey):
            for n, chunk in enumerate(chunks):
                url = f"{ACS_BASE}/{year}/acs/{survey}"
                params = {"get": ",".join(["NAME", *chunk]), "for": "state:*", "key": key}
                resp = ctx.http.get(url, params=params)
                art = ctx.write_bytes(
                    resp.content,
                    f"acs_{survey}_{year}_part{n}.json",
                    url=url,
                    params=params,
                    http_status=resp.status_code,
                    note=f"ACS {survey} {year} chunk {n}",
                )
                art.extra = {"year": year, "survey": survey, "part": n}
                artifacts.append(art)
        return artifacts

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        groups: dict[tuple[int, str], list[RawArtifact]] = {}
        for art in artifacts:
            if not art.path.suffix == ".json":
                continue
            year = art.extra.get("year")
            survey = art.extra.get("survey")
            if year is None:
                stem = art.path.stem  # acs_{survey}_{year}_part{n}
                _, survey, year, _ = stem.split("_")
            groups.setdefault((int(year), str(survey)), []).append(art)
        frames = []
        for (year, survey), arts in sorted(groups.items()):
            parsed = [
                parse_acs_json(json.loads(a.path.read_text(encoding="utf-8")))
                for a in sorted(arts, key=lambda a: a.path.name)
            ]
            frame = normalize_acs(parsed, year, survey)
            frame["source_url"] = f"{ACS_BASE}/{year}/acs/{survey}"
            frames.append(frame)
        if not frames:
            raise ParserError("no ACS JSON artifacts to parse")
        return pd.concat(frames, ignore_index=True)


def _read_text(path: Path) -> str:
    return open(path, encoding="utf-8").read()
