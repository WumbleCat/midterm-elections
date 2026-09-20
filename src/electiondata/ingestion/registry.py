"""Central source registry.

One :class:`SourceSpec` per dataset drives CLI listings, status reporting,
documentation generation and orchestration. Implementation status lives HERE
(and only here); ``docs/STATUS.md`` is generated from it plus the manifest.

Status semantics
----------------
DONE      connector exists, real source format handled, normalization works,
          tests pass, output written and verified with a live pull.
PARTIAL   works for a subset (years/variables) or with a documented caveat.
TODO      not implemented yet (may be feasible).
BLOCKED   connector implemented but cannot run here (credential/API key missing).
MANUAL    the source cannot be fetched automatically; an adapter parses a
          documented file format placed in data/raw/{source}/{dataset}/manual/.
DEFERRED  intentionally postponed (documented reason).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from ..exceptions import UnknownSourceError
from .base import Connector


class Phase(IntEnum):
    CORE = 1
    DEMOGRAPHICS = 2
    ECONOMICS = 3
    POLITICAL = 4
    ENVIRONMENT = 5
    SUPPLEMENTARY = 6


PHASE_NAMES: dict[str, Phase] = {
    "core": Phase.CORE,
    "demographics": Phase.DEMOGRAPHICS,
    "economics": Phase.ECONOMICS,
    "political": Phase.POLITICAL,
    "environment": Phase.ENVIRONMENT,
    "supplementary": Phase.SUPPLEMENTARY,
}


class Status(StrEnum):
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    TODO = "TODO"
    BLOCKED = "BLOCKED"
    MANUAL = "MANUAL"
    DEFERRED = "DEFERRED"


class AccessMethod(StrEnum):
    API = "api"
    BULK_FILE = "bulk_file"
    DOWNLOAD_TABLE = "download_table"
    STANDARDIZED_DATASET = "standardized_dataset"
    MANUAL = "manual"
    SCRAPE = "scrape"


@dataclass(frozen=True)
class SourceSpec:
    id: str
    source: str
    source_name: str
    dataset_name: str
    phase: Phase
    frequency: str
    geography: str
    access_method: AccessMethod
    status: Status
    authoritative_url: str
    description: str
    normalized_table: str
    raw_table: str = ""
    requires_api_key: str | None = None  # env var name
    connector: str | None = None  # "module:Class"
    variables: tuple[str, ...] = ()
    known_limitations: str = ""
    update_frequency: str = ""
    tested: bool = False  # unit tests with recorded fixtures exist
    options: dict[str, str] = field(default_factory=dict)  # documented ingest options

    @property
    def runnable(self) -> bool:
        return self.connector is not None and self.status in {Status.DONE, Status.PARTIAL, Status.BLOCKED, Status.MANUAL}

    def load_connector(self) -> Connector:
        if not self.connector:
            raise UnknownSourceError(f"dataset {self.id!r} has no connector (status={self.status})")
        module_name, _, cls_name = self.connector.partition(":")
        module = importlib.import_module(module_name)
        cls = getattr(module, cls_name)
        return cls()


_SRC = "electiondata.ingestion.sources"

REGISTRY: dict[str, SourceSpec] = {
    s.id: s
    for s in (
        # ------------------------------------------------------------ phase 1
        SourceSpec(
            id="medsl-senate",
            source="MEDSL",
            source_name="MIT Election Data + Science Lab",
            dataset_name="U.S. Senate returns 1976-2024",
            phase=Phase.CORE,
            frequency="event (biennial)",
            geography="state",
            access_method=AccessMethod.STANDARDIZED_DATASET,
            status=Status.DONE,
            authoritative_url="https://doi.org/10.7910/DVN/PEJ5QU",
            description="Candidate-level general-election Senate returns, cleaned by MEDSL, from Harvard Dataverse.",
            normalized_table="election_results",
            raw_table="medsl_senate_raw",
            connector=f"{_SRC}.medsl:SenateResultsConnector",
            variables=("year", "state", "office", "candidate", "party_detailed", "party_simplified", "candidatevotes", "totalvotes", "special", "stage"),
            known_limitations="General-election stage only; Louisiana jungle primaries and runoffs follow MEDSL conventions. Dataset versions replace earlier ones (revision_vintage = Dataverse version).",
            update_frequency="MEDSL republishes after each federal election (months later).",
            tested=True,
        ),
        SourceSpec(
            id="medsl-president",
            source="MEDSL",
            source_name="MIT Election Data + Science Lab",
            dataset_name="Presidential returns by state 1976-2024",
            phase=Phase.CORE,
            frequency="event (quadrennial)",
            geography="state",
            access_method=AccessMethod.STANDARDIZED_DATASET,
            status=Status.DONE,
            authoritative_url="https://doi.org/10.7910/DVN/42MVDX",
            description="State-level presidential returns by candidate, cleaned by MEDSL.",
            normalized_table="election_results",
            raw_table="medsl_president_raw",
            connector=f"{_SRC}.medsl:PresidentResultsConnector",
            variables=("year", "state", "candidate", "party_detailed", "party_simplified", "candidatevotes", "totalvotes", "writein"),
            known_limitations="Some states report fusion/ballot-line splits; votes are summed per candidate and party assigned from the largest line.",
            update_frequency="MEDSL republishes after each presidential election.",
            tested=True,
        ),
        SourceSpec(
            id="medsl-house",
            source="MEDSL",
            source_name="MIT Election Data + Science Lab",
            dataset_name="U.S. House returns 1976-2024",
            phase=Phase.CORE,
            frequency="event (biennial)",
            geography="congressional_district",
            access_method=AccessMethod.MANUAL,
            status=Status.MANUAL,
            authoritative_url="https://doi.org/10.7910/DVN/IG0UN2",
            description="District-level House returns by candidate, cleaned by MEDSL. The Dataverse file is behind a guestbook (terms acknowledgement) that the API refuses, so download 1976-2024-house.tab in a browser and place it in data/raw/medsl/medsl-house/manual/.",
            normalized_table="election_results",
            raw_table="medsl_house_raw",
            connector=f"{_SRC}.medsl:HouseResultsConnector",
            variables=("year", "state", "district", "candidate", "party", "candidatevotes", "totalvotes", "runoff", "special", "fusion_ticket"),
            known_limitations="Guestbook-gated download (API returns 'You may not download this file without the required Guestbook response'). Parser is fixture-tested on the documented 1976-2024 layout; vote 'mode' rows are collapsed (TOTAL preferred, otherwise summed) and runoff rows are excluded.",
            update_frequency="MEDSL republishes after each federal election.",
            tested=True,
        ),
        SourceSpec(
            id="fec-election-results",
            source="FEC",
            source_name="Federal Election Commission",
            dataset_name="Federal Elections official results (Excel)",
            phase=Phase.CORE,
            frequency="event (biennial)",
            geography="state / district",
            access_method=AccessMethod.DOWNLOAD_TABLE,
            status=Status.TODO,
            authoritative_url="https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/",
            description="Official certified federal results published by the FEC as multi-sheet Excel workbooks (federalelections{year}.xlsx).",
            normalized_table="election_results",
            raw_table="fec_election_results_raw",
            variables=("STATE", "CANDIDATE NAME", "PARTY", "GENERAL VOTES", "GENERAL %", "GE WINNER INDICATOR"),
            known_limitations="Workbook layouts differ by year (sheet names, header rows, footnotes); parser not yet written. Files verified reachable at https://www.fec.gov/resources/cms-content/documents/federalelections{year}.xlsx for 2020/2022.",
            update_frequency="Once per election, ~12 months after election day.",
        ),
        SourceSpec(
            id="eac-eavs",
            source="EAC",
            source_name="U.S. Election Assistance Commission",
            dataset_name="Election Administration and Voting Survey (EAVS)",
            phase=Phase.CORE,
            frequency="biennial",
            geography="jurisdiction -> aggregated to state",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.eac.gov/research-and-data/datasets-codebooks-and-surveys",
            description="Registration, ballots cast, mail/early/provisional voting by jurisdiction; aggregated to state level.",
            normalized_table="turnout",
            raw_table="eavs_raw",
            connector=f"{_SRC}.eac:EavsConnector",
            variables=("A1a", "A1b", "A1c", "C1a", "C1b", "E1a", "F1a", "F1b", "F1c", "F1d", "F1e", "F1f"),
            known_limitations="Only 2020, 2022 and 2024 public-release CSVs have stable URLs and a consistent item numbering; earlier years use different variable names. Negative EAVS codes (-88/-99 etc.) are treated as missing. Jurisdiction non-response is reported in n_jurisdictions_missing_ballots.",
            update_frequency="Published ~June of the year after the election; revised versions later.",
            tested=True,
            options={"years": "comma-separated EAVS years to ingest (default: 2020,2022,2024)"},
        ),
        # ------------------------------------------------------------ phase 2
        SourceSpec(
            id="census-acs-profile",
            source="Census",
            source_name="U.S. Census Bureau — American Community Survey",
            dataset_name="ACS 1-year state profile (age, sex, education, income, inequality, poverty, race/ethnicity, citizenship)",
            phase=Phase.DEMOGRAPHICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.BLOCKED,
            authoritative_url="https://api.census.gov/data.html",
            description="Detailed tables B01001, B01002, B15003, B19013, B19025/B11001, B19301, B19083, B17001, B03002, B05002, B05003 fetched from the Census API and reduced to one row per state-year.",
            normalized_table="demographics",
            raw_table="acs_raw",
            requires_api_key="CENSUS_API_KEY",
            connector=f"{_SRC}.census:AcsProfileConnector",
            variables=("B01003_001E", "B01002_001E", "B01001_*", "B15003_*", "B19013_001E", "B19301_001E", "B19083_001E", "B17001_*", "B03002_*", "B05002_*", "B05003_*"),
            known_limitations="The Census API now rejects keyless requests ('Missing Key'); set CENSUS_API_KEY. Connector is fixture-tested but has not run live. 2020 1-year estimates were not released (experimental only).",
            update_frequency="Annual, mid-September (1-year).",
            tested=True,
            options={"years": "comma-separated ACS years (default: 2010-latest)", "survey": "acs1 (default) or acs5"},
        ),
        SourceSpec(
            id="census-pep-population",
            source="Census",
            source_name="U.S. Census Bureau — Population Estimates Program",
            dataset_name="State population totals and components of change (vintages 2009, 2019, 2024)",
            phase=Phase.DEMOGRAPHICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.census.gov/programs-surveys/popest/data/data-sets.html",
            description="NST-EST alldata CSVs (2000-2010 intercensal, 2010-2019, 2020-2024) with population, births, deaths and domestic/international migration.",
            normalized_table="population",
            raw_table="pep_raw",
            connector=f"{_SRC}.census:PepPopulationConnector",
            variables=("POPESTIMATE*", "BIRTHS*", "DEATHS*", "INTERNATIONALMIG*", "DOMESTICMIG*", "NETMIG*", "RDOMESTICMIG*", "RNETMIG*"),
            known_limitations="Each vintage revises earlier years; all vintages are kept and distinguished by revision_vintage. The intercensal 2000-2010 file has no migration components in the same layout (population only).",
            update_frequency="New vintage every December.",
            tested=True,
        ),
        SourceSpec(
            id="census-gazetteer",
            source="Census",
            source_name="U.S. Census Bureau — Gazetteer files",
            dataset_name="State land and water area",
            phase=Phase.DEMOGRAPHICS,
            frequency="annual vintage (slow-moving)",
            geography="state",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html",
            description="Land area in square miles for population density (state files for 2024+, county files summed to states for earlier vintages).",
            normalized_table="geography",
            raw_table="gazetteer_raw",
            connector=f"{_SRC}.census:GazetteerConnector",
            variables=("GEOID", "ALAND_SQMI", "AWATER_SQMI"),
            update_frequency="Annual.",
            tested=True,
            options={"vintages": "comma-separated Gazetteer years (default 2012,2016,2020,2024)"},
        ),
        SourceSpec(
            id="census-urban-rural",
            source="Census",
            source_name="U.S. Census Bureau — Decennial urban/rural classification",
            dataset_name="2020 urban and rural population by county, aggregated to state",
            phase=Phase.DEMOGRAPHICS,
            frequency="decennial",
            geography="county -> state",
            access_method=AccessMethod.DOWNLOAD_TABLE,
            status=Status.DONE,
            authoritative_url="https://www.census.gov/programs-surveys/geography/guidance/geo-areas/urban-rural.html",
            description="2020_UA_COUNTY.xlsx urban/rural population per county summed to states.",
            normalized_table="urban_rural",
            raw_table="urban_rural_raw",
            connector=f"{_SRC}.census:UrbanRuralConnector",
            variables=("STATE", "COUNTY", "POP_COU", "POP_URB", "POP_RUR"),
            known_limitations="2020 only; 2010 classification (PctUrbanRural_State.xls) not yet parsed.",
            update_frequency="Decennial.",
            tested=True,
        ),
        SourceSpec(
            id="census-migration-flows",
            source="Census",
            source_name="U.S. Census Bureau — ACS state-to-state migration flows",
            dataset_name="State-to-state migration flows",
            phase=Phase.DEMOGRAPHICS,
            frequency="annual",
            geography="state pairs",
            access_method=AccessMethod.DOWNLOAD_TABLE,
            status=Status.TODO,
            authoritative_url="https://www.census.gov/topics/population/migration/guidance/state-to-state-migration-flows.html",
            description="Origin-destination mover counts published as multi-header Excel tables (State_to_State_Migration_Table_{year}.xlsx).",
            normalized_table="migration_flows",
            raw_table="migration_flows_raw",
            known_limitations="Excel layout has merged multi-row headers and MOE columns interleaved; parser not written. Net domestic migration is already available from census-pep-population.",
            update_frequency="Annual.",
        ),
        # ------------------------------------------------------------ phase 3
        SourceSpec(
            id="bls-laus",
            source="BLS",
            source_name="Bureau of Labor Statistics — Local Area Unemployment Statistics",
            dataset_name="State monthly labour force, employment, unemployment, unemployment rate (seasonally adjusted)",
            phase=Phase.ECONOMICS,
            frequency="monthly",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.DONE,
            authoritative_url="https://www.bls.gov/lau/",
            description="BLS Public Data API time series LASST{fips}0000000000003/4/5/6 for the 50 states + DC.",
            normalized_table="labor",
            raw_table="bls_laus_raw",
            requires_api_key=None,
            connector=f"{_SRC}.bls:LausConnector",
            variables=("unemployment_rate", "unemployment", "employment", "labor_force"),
            known_limitations="Without BLS_API_KEY the v1 API allows 25 series/query, 10 years/query and 25 queries/day: the default pull covers the last 10 years. The API returns the current vintage only; publication_date is estimated from the release calendar (month end + 21 days).",
            update_frequency="Monthly (~3 weeks after the reference month).",
            tested=True,
            options={"start_year": "first year (default: current-9 without key, current-19 with key)", "end_year": "last year (default current)"},
        ),
        SourceSpec(
            id="bls-cpi",
            source="BLS",
            source_name="Bureau of Labor Statistics — Consumer Price Index",
            dataset_name="CPI-U all items and core (national, NSA and SA)",
            phase=Phase.ECONOMICS,
            frequency="monthly",
            geography="nation",
            access_method=AccessMethod.API,
            status=Status.DONE,
            authoritative_url="https://www.bls.gov/cpi/",
            description="Series CUUR0000SA0, CUSR0000SA0, CUUR0000SA0L1E, CUSR0000SA0L1E.",
            normalized_table="national_economy",
            raw_table="bls_cpi_raw",
            connector=f"{_SRC}.bls:CpiConnector",
            variables=("cpi_all_items", "cpi_core"),
            known_limitations="publication_date estimated (month end + 15 days).",
            update_frequency="Monthly.",
            tested=True,
            options={"start_year": "first year (default 1996)", "end_year": "last year"},
        ),
        SourceSpec(
            id="bls-ces-national",
            source="BLS",
            source_name="Bureau of Labor Statistics — Current Employment Statistics / CPS",
            dataset_name="National nonfarm payrolls, average hourly earnings, unemployment rate, participation rate",
            phase=Phase.ECONOMICS,
            frequency="monthly",
            geography="nation",
            access_method=AccessMethod.API,
            status=Status.DONE,
            authoritative_url="https://www.bls.gov/ces/",
            description="Series CES0000000001, CES0500000003, LNS14000000, LNS11300000.",
            normalized_table="national_economy",
            raw_table="bls_ces_raw",
            connector=f"{_SRC}.bls:CesNationalConnector",
            variables=("nonfarm_payrolls", "average_hourly_earnings", "unemployment_rate", "labor_force_participation_rate"),
            known_limitations="Current vintage only; payroll revisions are not tracked. publication_date estimated (month end + 8 days).",
            update_frequency="Monthly (first Friday).",
            tested=True,
            options={"start_year": "first year (default 1996)", "end_year": "last year"},
        ),
        SourceSpec(
            id="bls-qcew",
            source="BLS",
            source_name="Bureau of Labor Statistics — Quarterly Census of Employment and Wages",
            dataset_name="State annual employment/wages by industry (QCEW open data)",
            phase=Phase.ECONOMICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.bls.gov/cew/additional-resources/open-data/",
            description="Per-industry annual CSV slices (data.bls.gov/cew/data/api/{year}/a/industry/{code}.csv) filtered to state rows for total, supersectors and NAICS sectors.",
            normalized_table="industry",
            raw_table="bls_qcew_raw",
            connector=f"{_SRC}.bls:QcewConnector",
            variables=("annual_avg_emplvl", "total_annual_wages", "annual_avg_estabs", "annual_avg_wkly_wage", "avg_annual_pay"),
            known_limitations="Default pull covers a small year range (option years). Suppressed cells are null.",
            update_frequency="Annual averages ~June of the following year.",
            tested=True,
            options={"years": "comma-separated years (default: latest 2 available)"},
        ),
        SourceSpec(
            id="bea-state-gdp",
            source="BEA",
            source_name="Bureau of Economic Analysis — Regional Economic Accounts",
            dataset_name="Annual state real and nominal GDP (SAGDP9N, SAGDP2N)",
            phase=Phase.ECONOMICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.BLOCKED,
            authoritative_url="https://apps.bea.gov/api/",
            description="BEA Regional API, TableName SAGDP9N (real GDP, chained dollars) and SAGDP2N (current dollars), LineCode 1 (all industries).",
            normalized_table="state_economy",
            raw_table="bea_gdp_raw",
            requires_api_key="BEA_API_KEY",
            connector=f"{_SRC}.bea:StateGdpConnector",
            variables=("real_gdp", "nominal_gdp"),
            known_limitations="Requires BEA_API_KEY (free). Fixture-tested, not yet run live. Current vintage only; comprehensive revisions are not tracked.",
            update_frequency="Annual (with quarterly updates).",
            tested=True,
        ),
        SourceSpec(
            id="bea-personal-income",
            source="BEA",
            source_name="Bureau of Economic Analysis — Regional Economic Accounts",
            dataset_name="Annual state personal income and per-capita personal income (SAINC1)",
            phase=Phase.ECONOMICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.BLOCKED,
            authoritative_url="https://apps.bea.gov/api/",
            description="BEA Regional API, TableName SAINC1 LineCode 1 (personal income), 2 (population), 3 (per capita).",
            normalized_table="state_economy",
            raw_table="bea_income_raw",
            requires_api_key="BEA_API_KEY",
            connector=f"{_SRC}.bea:PersonalIncomeConnector",
            variables=("personal_income", "per_capita_personal_income"),
            known_limitations="Requires BEA_API_KEY. Fixture-tested, not yet run live.",
            update_frequency="Annual.",
            tested=True,
        ),
        SourceSpec(
            id="bea-rpp",
            source="BEA",
            source_name="Bureau of Economic Analysis — Regional Price Parities",
            dataset_name="State regional price parities and real personal income (SARPP, SARPI)",
            phase=Phase.ECONOMICS,
            frequency="annual",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.BLOCKED,
            authoritative_url="https://apps.bea.gov/api/",
            description="BEA Regional API TableName SARPP LineCode 1 (RPP all items) and SARPI LineCode 1/2 (real personal income, real per capita).",
            normalized_table="state_economy",
            raw_table="bea_rpp_raw",
            requires_api_key="BEA_API_KEY",
            connector=f"{_SRC}.bea:RppConnector",
            variables=("regional_price_parity", "real_personal_income", "real_per_capita_personal_income"),
            known_limitations="Requires BEA_API_KEY. Fixture-tested, not yet run live.",
            update_frequency="Annual (December).",
            tested=True,
        ),
        # ------------------------------------------------------------ phase 4
        SourceSpec(
            id="fec-candidate-master",
            source="FEC",
            source_name="Federal Election Commission — bulk data",
            dataset_name="Candidate master file (cn{yy}.zip) by cycle",
            phase=Phase.POLITICAL,
            frequency="continuous (snapshot per retrieval)",
            geography="state / district",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.fec.gov/campaign-finance-data/candidate-master-file-description/",
            description="All registered federal candidates with party, office, state, district and incumbent/challenger/open status.",
            normalized_table="candidates",
            raw_table="fec_cn_raw",
            connector=f"{_SRC}.fec:CandidateMasterConnector",
            variables=("CAND_ID", "CAND_NAME", "CAND_PTY_AFFILIATION", "CAND_ELECTION_YR", "CAND_OFFICE_ST", "CAND_OFFICE", "CAND_OFFICE_DISTRICT", "CAND_ICI", "CAND_STATUS"),
            known_limitations="Includes non-serious filers; join with results/finance to select major candidates. Historical cycle files are the final snapshot for that cycle.",
            update_frequency="FEC refreshes bulk files nightly; historical cycles are frozen.",
            tested=True,
            options={"cycles": "comma-separated even years (default: 2010-current)"},
        ),
        SourceSpec(
            id="fec-candidate-finance",
            source="FEC",
            source_name="Federal Election Commission — bulk data",
            dataset_name="All candidates financial summary (weball{yy}.zip) by cycle",
            phase=Phase.POLITICAL,
            frequency="per report (snapshot per retrieval)",
            geography="state / district",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DONE,
            authoritative_url="https://www.fec.gov/campaign-finance-data/all-candidates-file-description/",
            description="Receipts, disbursements, cash on hand, debts and contribution breakdowns per candidate with the coverage end date of the latest report.",
            normalized_table="candidate_finance",
            raw_table="fec_weball_raw",
            connector=f"{_SRC}.fec:CandidateFinanceConnector",
            variables=("TTL_RECEIPTS", "TTL_DISB", "COH_COP", "DEBTS_OWED_BY", "TTL_INDIV_CONTRIB", "OTHER_POL_CMTE_CONTRIB", "POL_PTY_CONTRIB", "CVG_END_DT"),
            known_limitations="Historical cycle files hold the FINAL totals (coverage end 12/31); pre-election snapshots for past cycles are only available via FEC API report filings (todo: fec-committee-reports). Point-in-time filters therefore exclude finance for past elections unless a snapshot retrieved before election day exists.",
            update_frequency="Refreshed nightly during a cycle.",
            tested=True,
            options={"cycles": "comma-separated even years (default: 2010-current)"},
        ),
        SourceSpec(
            id="fec-committee-reports",
            source="FEC",
            source_name="Federal Election Commission — OpenFEC API",
            dataset_name="Candidate committee periodic reports (pre-election snapshots)",
            phase=Phase.POLITICAL,
            frequency="per report",
            geography="state / district",
            access_method=AccessMethod.API,
            status=Status.TODO,
            authoritative_url="https://api.open.fec.gov/developers/",
            description="/reports/{committee_type}/ filings with coverage_end_date and receipt_date, giving true point-in-time finance for historical backtests.",
            normalized_table="candidate_finance",
            raw_table="fec_reports_raw",
            requires_api_key="FEC_API_KEY",
            known_limitations="Not implemented. DEMO_KEY rate limits are low; a registered api.data.gov key is recommended.",
            update_frequency="Continuous.",
        ),
        SourceSpec(
            id="fec-independent-expenditures",
            source="FEC",
            source_name="Federal Election Commission — bulk data",
            dataset_name="Independent expenditures (outside spending)",
            phase=Phase.POLITICAL,
            frequency="per filing",
            geography="state / district",
            access_method=AccessMethod.BULK_FILE,
            status=Status.DEFERRED,
            authoritative_url="https://www.fec.gov/campaign-finance-data/independent-expenditures-file-description/",
            description="Support/oppose spending by outside groups per candidate.",
            normalized_table="candidate_finance",
            raw_table="fec_ie_raw",
            known_limitations="Deferred: second-stage feature per the specification; bulk files are large and need candidate matching.",
            update_frequency="Continuous.",
        ),
        # ------------------------------------------------------------ phase 5
        SourceSpec(
            id="polls-approval",
            source="Polling",
            source_name="Presidential approval polls (manual CSV adapter)",
            dataset_name="Presidential approval poll-level observations",
            phase=Phase.ENVIRONMENT,
            frequency="event (poll)",
            geography="nation",
            access_method=AccessMethod.MANUAL,
            status=Status.MANUAL,
            authoritative_url="https://news.gallup.com/poll/245606/update-gallup-presidential-approval-ratings.aspx",
            description="Poll-level approval data supplied as CSV in the documented template (see docs/DATA_SOURCES.md).",
            normalized_table="approval_polls",
            raw_table="approval_polls_raw",
            connector=f"{_SRC}.polling:ApprovalPollsConnector",
            variables=("poll_id", "pollster", "start_date", "end_date", "sample_size", "population_type", "approve", "disapprove", "publication_date"),
            known_limitations="No durable free structured source with poll-level history was identified (FiveThirtyEight feeds were discontinued in 2025; RealClearPolling has no API and scraping is out of scope). Gallup publishes tables, not downloads.",
            update_frequency="Manual.",
            tested=True,
        ),
        SourceSpec(
            id="polls-generic-ballot",
            source="Polling",
            source_name="Generic congressional ballot polls (manual CSV adapter)",
            dataset_name="Generic ballot poll-level observations",
            phase=Phase.ENVIRONMENT,
            frequency="event (poll)",
            geography="nation",
            access_method=AccessMethod.MANUAL,
            status=Status.MANUAL,
            authoritative_url="https://www.realclearpolling.com/polls/state-of-the-union/generic-congressional-vote",
            description="Poll-level generic ballot data supplied as CSV in the documented template.",
            normalized_table="generic_ballot_polls",
            raw_table="generic_ballot_raw",
            connector=f"{_SRC}.polling:GenericBallotConnector",
            variables=("poll_id", "pollster", "start_date", "end_date", "sample_size", "population_type", "generic_dem", "generic_rep", "publication_date"),
            known_limitations="Same as polls-approval.",
            update_frequency="Manual.",
            tested=True,
        ),
        SourceSpec(
            id="polls-races",
            source="Polling",
            source_name="Race-specific polls (manual CSV adapter)",
            dataset_name="State/district race poll-level observations",
            phase=Phase.ENVIRONMENT,
            frequency="event (poll)",
            geography="state / district",
            access_method=AccessMethod.MANUAL,
            status=Status.MANUAL,
            authoritative_url="https://www.realclearpolling.com/",
            description="Poll-level race polling supplied as CSV in the documented template.",
            normalized_table="polls",
            raw_table="polls_raw",
            connector=f"{_SRC}.polling:RacePollsConnector",
            variables=("poll_id", "state", "office", "year", "pollster", "start_date", "end_date", "sample_size", "population_type", "dem_pct", "rep_pct", "publication_date"),
            known_limitations="Same as polls-approval.",
            update_frequency="Manual.",
            tested=True,
        ),
        SourceSpec(
            id="special-elections",
            source="MEDSL/FEC/state offices",
            source_name="Special-election results",
            dataset_name="Special elections with partisan baselines",
            phase=Phase.ENVIRONMENT,
            frequency="event",
            geography="state / district",
            access_method=AccessMethod.MANUAL,
            status=Status.TODO,
            authoritative_url="https://electionlab.mit.edu/data",
            description="Special-election margins versus a baseline to measure national swing.",
            normalized_table="special_elections",
            raw_table="special_elections_raw",
            known_limitations="Not implemented: MEDSL flags specials for Senate/House (special=True rows are already in election_results) but baselines need district-level presidential results, which MEDSL does not publish.",
            update_frequency="Event-driven.",
        ),
        # ------------------------------------------------------------ phase 6
        SourceSpec(
            id="naep-state",
            source="NAEP",
            source_name="National Center for Education Statistics — NAEP Data Service",
            dataset_name="State average scale scores, grades 4 and 8, mathematics and reading",
            phase=Phase.SUPPLEMENTARY,
            frequency="biennial",
            geography="state",
            access_method=AccessMethod.API,
            status=Status.DONE,
            authoritative_url="https://www.nationsreportcard.gov/api_documentation.aspx",
            description="NAEP Data Service GetAdhocData endpoint (MN:MN average scores and achievement-level percentages).",
            normalized_table="naep",
            raw_table="naep_raw",
            connector=f"{_SRC}.naep:NaepStateConnector",
            variables=("average_score", "pct_at_or_above_basic", "pct_at_or_above_proficient", "pct_advanced"),
            known_limitations="Publication dates come from the release calendar rule (see release_calendar.naep).",
            update_frequency="Every two years.",
            tested=True,
            options={"years": "comma-separated assessment years (default: 2003-2024 NAEP years)"},
        ),
        SourceSpec(
            id="pew-religion",
            source="Pew",
            source_name="Pew Research Center — Religious Landscape Study",
            dataset_name="State religious composition by survey vintage (manual CSV adapter)",
            phase=Phase.SUPPLEMENTARY,
            frequency="occasional (2007, 2014, 2023-24)",
            geography="state",
            access_method=AccessMethod.MANUAL,
            status=Status.MANUAL,
            authoritative_url="https://www.pewresearch.org/religious-landscape-study/",
            description="State-level shares transcribed from Pew published tables or computed from the microdata (free account required) into the documented CSV template.",
            normalized_table="religion",
            raw_table="religion_raw",
            connector=f"{_SRC}.pew:ReligionConnector",
            variables=("pct_evangelical_protestant", "pct_mainline_protestant", "pct_catholic", "pct_religiously_unaffiliated", "pct_attend_weekly"),
            known_limitations="Pew microdata downloads require a registered account and accepting terms; no automated access.",
            update_frequency="Roughly every 7-10 years.",
            tested=True,
        ),
        SourceSpec(
            id="census-cps-voting",
            source="Census",
            source_name="U.S. Census Bureau — CPS Voting and Registration Supplement microdata",
            dataset_name="Respondent-level registration and turnout",
            phase=Phase.SUPPLEMENTARY,
            frequency="biennial",
            geography="respondent (state identified)",
            access_method=AccessMethod.API,
            status=Status.TODO,
            authoritative_url="https://www.census.gov/data/developers/data-sets/census-microdata-api/cps/voting.html",
            description="Microdata API (api.census.gov/data/{year}/cps/voting/nov) variables PES1 (voted), PES2 (registered), PRTAGE, PESEX, PTDTRACE, PEHSPNON, PEEDUCA, HEFAMINC, GESTFIPS, PWSSWGT.",
            normalized_table="individual_turnout_cps",
            raw_table="cps_voting_raw",
            requires_api_key="CENSUS_API_KEY",
            known_limitations="Not implemented; requires CENSUS_API_KEY and paging over ~100k respondents per year.",
            update_frequency="Biennial (April after the election).",
        ),
        SourceSpec(
            id="anes-timeseries",
            source="ANES",
            source_name="American National Election Studies — Time Series Cumulative Data File",
            dataset_name="Respondent-level vote choice, party ID, ideology, demographics",
            phase=Phase.SUPPLEMENTARY,
            frequency="biennial/quadrennial",
            geography="respondent",
            access_method=AccessMethod.MANUAL,
            status=Status.TODO,
            authoritative_url="https://electionstudies.org/data-center/",
            description="Cumulative CSV (anes_timeseries_cdf_csv_*.csv) downloaded manually after login.",
            normalized_table="individual_behavior_anes",
            raw_table="anes_raw",
            known_limitations="Requires a registered ANES account; variable recodes (VCF0301 party ID, VCF0803 ideology, VCF0705 presidential vote, ...) not yet written.",
            update_frequency="After each election study.",
        ),
    )
}


def get_spec(dataset_id: str) -> SourceSpec:
    try:
        return REGISTRY[dataset_id]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY))
        raise UnknownSourceError(f"unknown dataset {dataset_id!r}; known: {known}") from exc


def list_specs(
    *,
    phase: Phase | int | str | None = None,
    status: Status | str | None = None,
    source: str | None = None,
    runnable_only: bool = False,
) -> list[SourceSpec]:
    specs = list(REGISTRY.values())
    if phase is not None:
        phase_val = PHASE_NAMES[phase.lower()] if isinstance(phase, str) and not phase.isdigit() else Phase(int(phase))
        specs = [s for s in specs if s.phase == phase_val]
    if status is not None:
        specs = [s for s in specs if s.status == Status(str(status).upper())]
    if source is not None:
        specs = [s for s in specs if s.source.lower() == source.lower()]
    if runnable_only:
        specs = [s for s in specs if s.runnable]
    return sorted(specs, key=lambda s: (int(s.phase), s.id))


def status_counts() -> dict[str, int]:
    counts = dict.fromkeys(Status, 0)
    for s in REGISTRY.values():
        counts[s.status] += 1
    return {k.value: v for k, v in counts.items()}
