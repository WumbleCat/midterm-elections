"""Explicit schemas for every canonical table.

Each :class:`TableSchema` lists its columns, natural key, frequency and the
provenance columns that every row must carry for point-in-time correctness.
:func:`enforce_schema` coerces a DataFrame to the schema (adding missing
nullable columns, casting dtypes, ordering columns) and refuses frames that
lack required columns. ``docs/DATA_MODEL.md`` is generated from these objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..exceptions import NormalizationError

# ----------------------------------------------------------------- columns


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str  # string | int64 | float64 | bool | date | timestamp
    description: str = ""
    nullable: bool = True
    unit: str = ""


@dataclass(frozen=True)
class TableSchema:
    name: str
    description: str
    frequency: str
    key: tuple[str, ...]
    columns: tuple[Column, ...]
    provenance: bool = True
    derived: bool = False  # produced by transforms rather than ingestion
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_columns(self) -> tuple[Column, ...]:
        return self.columns + (PROVENANCE_COLUMNS if self.provenance else ())

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.all_columns]

    def column(self, name: str) -> Column:
        for c in self.all_columns:
            if c.name == name:
                return c
        raise KeyError(name)


# Point-in-time provenance carried by every ingested row.
PROVENANCE_COLUMNS: tuple[Column, ...] = (
    Column("observation_date", "date", "Date the observation refers to (period end for spans)."),
    Column("period_start", "date", "Start of the reference period, if the observation spans one."),
    Column("period_end", "date", "End of the reference period."),
    Column(
        "publication_date",
        "date",
        "Date the value became publicly available. Rows with publication_date > as_of are excluded by point-in-time filters.",
    ),
    Column(
        "publication_date_estimated",
        "bool",
        "True when publication_date comes from a documented release-lag rule rather than a recorded release date.",
        nullable=False,
    ),
    Column("retrieval_date", "date", "Date the raw file was downloaded.", nullable=False),
    Column("source", "string", "Short source id (MEDSL, BLS, ...).", nullable=False),
    Column("source_url", "string", "URL of the raw artifact (credentials redacted)."),
    Column("dataset_id", "string", "Registry dataset id that produced the row.", nullable=False),
    Column(
        "revision_vintage",
        "string",
        "Vintage/version of the upstream release (e.g. PEP vintage, MEDSL version).",
    ),
    Column("ingestion_run_id", "string", "Manifest run id.", nullable=False),
)

_STATE_COLS = (
    Column("state", "string", "USPS state abbreviation (canonical).", nullable=False),
    Column("state_fips", "string", "Two-digit state FIPS code.", nullable=False),
)


def _pct(name: str, desc: str) -> Column:
    return Column(name, "float64", desc, unit="share 0-1")


# ------------------------------------------------------------------ tables

ELECTION_RESULTS = TableSchema(
    name="election_results",
    description="Candidate-level general-election returns for federal offices (one row per candidate per race).",
    frequency="event (election)",
    key=("state", "year", "office", "district", "candidate", "party_raw", "special"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "Election year.", nullable=False),
        Column("election_date", "date", "Date of the general election."),
        Column("office", "string", "president | senate | house.", nullable=False),
        Column(
            "district",
            "string",
            "'statewide' for president/senate; zero-padded district number for house.",
            nullable=False,
        ),
        Column("election_type", "string", "general | special | primary | runoff.", nullable=False),
        Column("special", "bool", "True for special elections.", nullable=False),
        Column("candidate", "string", "Candidate name as reported (upper case)."),
        Column("party_raw", "string", "Party label exactly as reported by the source."),
        Column(
            "party",
            "string",
            "Canonical party: DEM | REP | LIB | GRN | IND | OTHER.",
            nullable=False,
        ),
        Column("writein", "bool", "Write-in candidate flag."),
        Column(
            "votes",
            "float64",
            "Votes received by the candidate (summed over vote modes).",
            unit="votes",
        ),
        Column(
            "total_votes",
            "float64",
            "Total votes cast in the race as reported by the source.",
            unit="votes",
        ),
        Column("unofficial", "bool", "Source flagged the result as unofficial."),
    ),
)

ELECTION_RACE_SUMMARY = TableSchema(
    name="election_race_summary",
    description="Race-level outcomes derived from election_results (Democratic/Republican/other totals, shares, margin, winner).",
    frequency="event (election)",
    key=("state", "year", "office", "district", "special"),
    derived=True,
    columns=_STATE_COLS
    + (
        Column("year", "int64", "", nullable=False),
        Column("election_date", "date", ""),
        Column("office", "string", "", nullable=False),
        Column("district", "string", "", nullable=False),
        Column("special", "bool", "", nullable=False),
        Column("dem_votes", "float64", "", unit="votes"),
        Column("rep_votes", "float64", "", unit="votes"),
        Column("other_votes", "float64", "", unit="votes"),
        Column("total_candidate_votes", "float64", "dem + rep + other", unit="votes"),
        Column("total_votes", "float64", "Total votes reported by the source.", unit="votes"),
        _pct("dem_vote_share", "dem_votes / total_candidate_votes"),
        _pct("rep_vote_share", "rep_votes / total_candidate_votes"),
        _pct("other_vote_share", "other_votes / total_candidate_votes"),
        _pct("dem_two_party_share", "dem_votes / (dem_votes + rep_votes)"),
        _pct("rep_two_party_share", "rep_votes / (dem_votes + rep_votes)"),
        Column(
            "dem_rep_margin",
            "float64",
            "dem_two_party_share - rep_two_party_share",
            unit="share -1..1",
        ),
        Column("winner_party", "string", "Party of the candidate with the most votes."),
        Column(
            "winning_margin",
            "float64",
            "Winner share minus runner-up share (of candidate votes).",
            unit="share",
        ),
        Column("dem_candidate", "string", "Top Democratic candidate."),
        Column("rep_candidate", "string", "Top Republican candidate."),
        Column("n_candidates", "int64", "Number of candidates with votes."),
        Column("uncontested", "bool", "True when only one of DEM/REP fielded a candidate."),
    ),
)

TURNOUT = TableSchema(
    name="turnout",
    description="State-level registration and ballots cast (EAVS, aggregated from jurisdictions).",
    frequency="biennial (federal general elections)",
    key=("state", "year"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "Election year.", nullable=False),
        Column(
            "registered_voters", "float64", "Total registered voters (EAVS A1a).", unit="persons"
        ),
        Column(
            "active_registered_voters", "float64", "Active registrations (A1b).", unit="persons"
        ),
        Column(
            "inactive_registered_voters", "float64", "Inactive registrations (A1c).", unit="persons"
        ),
        Column(
            "citizen_voting_age_population",
            "float64",
            "CVAP; null unless joined from ACS.",
            unit="persons",
        ),
        Column(
            "voting_age_population",
            "float64",
            "VAP; null unless joined from PEP age tables.",
            unit="persons",
        ),
        Column(
            "ballots_cast",
            "float64",
            "Total ballots counted / voters who participated (F1a).",
            unit="ballots",
        ),
        Column("in_person_election_day_votes", "float64", "F1b", unit="ballots"),
        Column("early_votes", "float64", "In-person early votes (F1c).", unit="ballots"),
        Column("mail_votes", "float64", "Mail ballots counted (F1d).", unit="ballots"),
        Column(
            "provisional_votes", "float64", "Provisional ballots counted (F1e).", unit="ballots"
        ),
        Column("uocava_votes", "float64", "UOCAVA ballots counted (F1f).", unit="ballots"),
        Column("mail_ballots_transmitted", "float64", "Mail ballots sent (C1a).", unit="ballots"),
        Column("mail_ballots_returned", "float64", "Mail ballots returned (C1b).", unit="ballots"),
        Column(
            "mail_ballots_rejected",
            "float64",
            "Mail ballots rejected (C4a where present).",
            unit="ballots",
        ),
        Column("provisional_ballots_submitted", "float64", "E1a", unit="ballots"),
        Column("n_jurisdictions", "int64", "Jurisdictions aggregated."),
        Column(
            "n_jurisdictions_missing_ballots",
            "int64",
            "Jurisdictions with no usable ballots_cast value.",
        ),
    ),
)

DEMOGRAPHICS = TableSchema(
    name="demographics",
    description="State-year demographic profile (ACS). One row per state × survey year × survey product. Shares are 0-1.",
    frequency="annual (ACS 1-year); 5-year product stored separately by `survey`",
    key=("state", "year", "survey"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "ACS reference year.", nullable=False),
        Column("survey", "string", "acs1 | acs5", nullable=False),
        Column("total_population", "float64", "", unit="persons"),
        Column("median_age", "float64", "", unit="years"),
        _pct("pct_under_18", ""),
        _pct("pct_18_24", ""),
        _pct("pct_25_34", ""),
        _pct("pct_35_44", ""),
        _pct("pct_45_54", ""),
        _pct("pct_55_64", ""),
        _pct("pct_65_74", ""),
        _pct("pct_75_plus", ""),
        _pct("pct_65_plus", ""),
        _pct("pct_male", ""),
        _pct("pct_female", ""),
        _pct("pct_less_than_high_school", "Population 25+."),
        _pct("pct_high_school", ""),
        _pct("pct_some_college", ""),
        _pct("pct_associate_degree", ""),
        _pct("pct_bachelors", ""),
        _pct("pct_graduate_degree", ""),
        _pct("pct_bachelors_or_higher", ""),
        _pct("pct_high_school_or_higher", ""),
        Column("median_household_income", "float64", "", unit="USD (current)"),
        Column("mean_household_income", "float64", "", unit="USD (current)"),
        Column("per_capita_income", "float64", "", unit="USD (current)"),
        Column("gini_coefficient", "float64", "", unit="0-1"),
        _pct(
            "poverty_rate",
            "Population below poverty level / population for whom poverty status is determined.",
        ),
        _pct("pct_white", ""),
        _pct("pct_white_non_hispanic", ""),
        _pct("pct_black", ""),
        _pct("pct_hispanic_latino", ""),
        _pct("pct_asian", ""),
        _pct("pct_native_american", ""),
        _pct("pct_native_hawaiian_pacific_islander", ""),
        _pct("pct_multiracial", ""),
        _pct("pct_other_race", ""),
        _pct("pct_foreign_born", ""),
        _pct("pct_naturalized_citizen", ""),
        _pct("pct_non_citizen", ""),
        _pct("pct_native_born", ""),
        Column(
            "citizen_voting_age_population", "float64", "Citizens 18+ (B05003).", unit="persons"
        ),
    ),
)

POPULATION = TableSchema(
    name="population",
    description="Annual state population estimates and components of change (Census PEP). Each vintage is stored separately.",
    frequency="annual (July 1 estimates)",
    key=("state", "year", "revision_vintage"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "Estimate year (July 1).", nullable=False),
        Column("population", "float64", "", unit="persons"),
        Column("births", "float64", "", unit="persons"),
        Column("deaths", "float64", "", unit="persons"),
        Column("natural_change", "float64", "", unit="persons (net)"),
        Column(
            "international_migration",
            "float64",
            "Net international migration.",
            unit="persons (net)",
        ),
        Column("domestic_migration", "float64", "Net domestic migration.", unit="persons (net)"),
        Column(
            "net_migration",
            "float64",
            "Net migration (international + domestic).",
            unit="persons (net)",
        ),
        Column(
            "domestic_migration_rate",
            "float64",
            "Per 1,000 population (PEP RDOMESTICMIG).",
            unit="per 1000",
        ),
        Column(
            "net_migration_rate", "float64", "Per 1,000 population (PEP RNETMIG).", unit="per 1000"
        ),
    ),
)

GEOGRAPHY = TableSchema(
    name="geography",
    description="State land/water area from Census Gazetteer files (used for population density).",
    frequency="annual (Gazetteer vintage)",
    key=("state", "year"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "Gazetteer vintage year.", nullable=False),
        Column("land_area_sq_miles", "float64", "", unit="sq mi"),
        Column("water_area_sq_miles", "float64", "", unit="sq mi"),
    ),
)

URBAN_RURAL = TableSchema(
    name="urban_rural",
    description="Urban/rural population by state from decennial census classifications (not annual).",
    frequency="decennial",
    key=("state", "year"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "Census year of the classification.", nullable=False),
        Column("total_population", "float64", "", unit="persons"),
        Column("urban_population", "float64", "", unit="persons"),
        Column("rural_population", "float64", "", unit="persons"),
        _pct("pct_urban", ""),
        _pct("pct_rural", ""),
    ),
)

MIGRATION_FLOWS = TableSchema(
    name="migration_flows",
    description="State-to-state migration flows (ACS). One row per origin × destination × year.",
    frequency="annual (ACS 1-year)",
    key=("origin_state", "destination_state", "year"),
    columns=(
        Column("origin_state", "string", "USPS abbr of prior residence.", nullable=False),
        Column("destination_state", "string", "USPS abbr of current residence.", nullable=False),
        Column("year", "int64", "", nullable=False),
        Column("movers", "float64", "Estimated persons who moved.", unit="persons"),
        Column("movers_moe", "float64", "Margin of error.", unit="persons"),
    ),
)

LABOR = TableSchema(
    name="labor",
    description="Monthly state labour-market series (BLS LAUS). Values are the vintage current at retrieval; the API does not expose historical revisions.",
    frequency="monthly",
    key=("state", "date", "seasonally_adjusted"),
    columns=_STATE_COLS
    + (
        Column("date", "date", "First day of the reference month.", nullable=False),
        Column("seasonally_adjusted", "bool", "", nullable=False),
        Column("labor_force", "float64", "", unit="persons"),
        Column("employment", "float64", "", unit="persons"),
        Column("unemployment", "float64", "", unit="persons"),
        Column(
            "unemployment_rate",
            "float64",
            "Percent (0-100) as published by BLS.",
            unit="percent 0-100",
        ),
    ),
    notes=("unemployment_rate is stored in BLS units (percent 0-100), not a 0-1 share.",),
)

INDUSTRY = TableSchema(
    name="industry",
    description="Annual state employment, wages and establishments by industry (BLS QCEW annual averages).",
    frequency="annual",
    key=("state", "year", "industry_code", "own_code"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "", nullable=False),
        Column(
            "industry_code",
            "string",
            "QCEW industry code (10 = total, NAICS supersectors, sectors).",
            nullable=False,
        ),
        Column(
            "own_code",
            "string",
            "Ownership code (0 = total covered, 5 = private, 1-3 = government).",
            nullable=False,
        ),
        Column("agglvl_code", "string", "QCEW aggregation level code."),
        Column("annual_avg_establishments", "float64", "", unit="establishments"),
        Column("annual_avg_employment", "float64", "", unit="persons"),
        Column("total_annual_wages", "float64", "", unit="USD"),
        Column("annual_avg_weekly_wage", "float64", "", unit="USD"),
        Column("avg_annual_pay", "float64", "", unit="USD"),
    ),
)

STATE_ECONOMY = TableSchema(
    name="state_economy",
    description="Annual state GDP, personal income and regional price parities (BEA Regional Accounts).",
    frequency="annual",
    key=("state", "year", "measure"),
    columns=_STATE_COLS
    + (
        Column("year", "int64", "", nullable=False),
        Column(
            "measure",
            "string",
            "real_gdp | nominal_gdp | personal_income | per_capita_personal_income | regional_price_parity | real_personal_income | ...",
            nullable=False,
        ),
        Column("value", "float64", ""),
        Column(
            "unit", "string", "Unit as published by BEA (e.g. millions of chained 2017 dollars)."
        ),
        Column("bea_table", "string", "BEA table name (SAGDP9N, SAINC1, SARPP, ...)."),
        Column("line_code", "string", "BEA line code."),
    ),
)

NATIONAL_ECONOMY = TableSchema(
    name="national_economy",
    description="Monthly national series (BLS CPI, CES payrolls/earnings, CPS unemployment & participation). Long format.",
    frequency="monthly",
    key=("date", "series_id"),
    columns=(
        Column("date", "date", "First day of the reference month.", nullable=False),
        Column("series_id", "string", "BLS series id.", nullable=False),
        Column(
            "measure",
            "string",
            "cpi_all_items | cpi_core | nonfarm_payrolls | average_hourly_earnings | unemployment_rate | labor_force_participation_rate",
            nullable=False,
        ),
        Column("value", "float64", ""),
        Column("seasonally_adjusted", "bool", ""),
        Column("unit", "string", "index 1982-84=100 | thousands | USD | percent"),
    ),
)

CANDIDATES = TableSchema(
    name="candidates",
    description="Candidate identity and incumbency (FEC candidate master, one row per candidate × cycle).",
    frequency="continuous (bulk file refreshed by FEC); snapshot per retrieval",
    key=("candidate_id", "cycle"),
    columns=(
        Column("candidate_id", "string", "FEC candidate id.", nullable=False),
        Column("cycle", "int64", "Two-year election cycle (file year).", nullable=False),
        Column(
            "election_year", "int64", "Year of the candidate's election (FEC CAND_ELECTION_YR)."
        ),
        Column("name", "string", ""),
        Column("party_raw", "string", "FEC party code."),
        Column("party", "string", "Canonical party."),
        Column("office", "string", "president | senate | house"),
        Column("state", "string", "USPS abbr; 'US' for president."),
        Column("state_fips", "string", ""),
        Column(
            "district",
            "string",
            "Zero-padded district; 'statewide' for senate; '00' style raw preserved in district_raw.",
        ),
        Column("district_raw", "string", ""),
        Column(
            "incumbent_challenger_status", "string", "I = incumbent, C = challenger, O = open seat."
        ),
        Column(
            "candidate_status",
            "string",
            "C = statutory candidate, F = future, N = not yet, P = prior.",
        ),
        Column("principal_committee_id", "string", ""),
    ),
)

CANDIDATE_FINANCE = TableSchema(
    name="candidate_finance",
    description="Candidate financial summaries (FEC 'all candidates' summary file). coverage_end_date is the reporting period end; publication_date approximates the filing deadline.",
    frequency="per report (snapshot files refreshed by FEC)",
    key=("candidate_id", "cycle", "coverage_end_date", "revision_vintage"),
    columns=(
        Column("candidate_id", "string", "", nullable=False),
        Column("cycle", "int64", "", nullable=False),
        Column("name", "string", ""),
        Column("party_raw", "string", ""),
        Column("party", "string", ""),
        Column("office", "string", ""),
        Column("state", "string", ""),
        Column("state_fips", "string", ""),
        Column("district", "string", ""),
        Column("incumbent_challenger_status", "string", ""),
        Column(
            "coverage_end_date", "date", "End of the period covered by the totals.", nullable=False
        ),
        Column("total_receipts", "float64", "", unit="USD"),
        Column("transfers_from_authorized", "float64", "", unit="USD"),
        Column("total_disbursements", "float64", "", unit="USD"),
        Column("transfers_to_authorized", "float64", "", unit="USD"),
        Column("cash_on_hand_beginning", "float64", "", unit="USD"),
        Column("cash_on_hand_end", "float64", "", unit="USD"),
        Column("candidate_contributions", "float64", "Self-financing contributions.", unit="USD"),
        Column("candidate_loans", "float64", "", unit="USD"),
        Column("other_loans", "float64", "", unit="USD"),
        Column("candidate_loan_repayments", "float64", "", unit="USD"),
        Column("other_loan_repayments", "float64", "", unit="USD"),
        Column("debts_owed_by", "float64", "", unit="USD"),
        Column("individual_contributions", "float64", "", unit="USD"),
        Column("other_committee_contributions", "float64", "PAC contributions.", unit="USD"),
        Column("party_contributions", "float64", "", unit="USD"),
        Column("refunds_individual", "float64", "", unit="USD"),
        Column("refunds_committee", "float64", "", unit="USD"),
    ),
)

POLLS = TableSchema(
    name="polls",
    description="Race-specific poll observations (one row per poll × race). Populated via the manual CSV adapter until a durable structured source is chosen.",
    frequency="event (poll)",
    key=("poll_id", "state", "office", "district", "year"),
    columns=(
        Column("poll_id", "string", "", nullable=False),
        Column("state", "string", "", nullable=False),
        Column("state_fips", "string", ""),
        Column("district", "string", "'statewide' or district number."),
        Column("office", "string", "", nullable=False),
        Column("year", "int64", "Election year.", nullable=False),
        Column("pollster", "string", ""),
        Column("pollster_grade", "string", ""),
        Column("sponsor", "string", ""),
        Column("start_date", "date", "Field start."),
        Column("end_date", "date", "Field end."),
        Column("sample_size", "float64", ""),
        Column("population_type", "string", "lv | rv | a"),
        Column("mode", "string", ""),
        Column("dem_candidate", "string", ""),
        Column("rep_candidate", "string", ""),
        _pct("dem_pct", "Democratic share as 0-1."),
        _pct("rep_pct", ""),
        _pct("other_pct", ""),
        _pct("undecided_pct", ""),
        Column("poll_margin", "float64", "dem_pct - rep_pct", unit="share"),
    ),
)

APPROVAL_POLLS = TableSchema(
    name="approval_polls",
    description="Presidential approval poll observations.",
    frequency="event (poll)",
    key=("poll_id",),
    columns=(
        Column("poll_id", "string", "", nullable=False),
        Column("pollster", "string", ""),
        Column("president", "string", ""),
        Column("start_date", "date", ""),
        Column("end_date", "date", ""),
        Column("sample_size", "float64", ""),
        Column("population_type", "string", ""),
        _pct("approve", ""),
        _pct("disapprove", ""),
        Column("net_approval", "float64", "approve - disapprove", unit="share"),
    ),
)

GENERIC_BALLOT_POLLS = TableSchema(
    name="generic_ballot_polls",
    description="Generic congressional ballot poll observations.",
    frequency="event (poll)",
    key=("poll_id",),
    columns=(
        Column("poll_id", "string", "", nullable=False),
        Column("pollster", "string", ""),
        Column("start_date", "date", ""),
        Column("end_date", "date", ""),
        Column("sample_size", "float64", ""),
        Column("population_type", "string", ""),
        _pct("generic_dem", ""),
        _pct("generic_rep", ""),
        _pct("generic_other", ""),
        _pct("undecided", ""),
        Column("generic_margin", "float64", "generic_dem - generic_rep", unit="share"),
    ),
)

SPECIAL_ELECTIONS = TableSchema(
    name="special_elections",
    description="Special-election results with a partisan baseline for swing computation.",
    frequency="event",
    key=("state", "district", "office", "election_date"),
    columns=(
        Column("state", "string", "", nullable=False),
        Column("state_fips", "string", ""),
        Column("district", "string", ""),
        Column("office", "string", "", nullable=False),
        Column("election_date", "date", "", nullable=False),
        _pct("dem_vote_share", ""),
        _pct("rep_vote_share", ""),
        Column("actual_margin", "float64", "dem - rep", unit="share"),
        Column(
            "historical_baseline_margin",
            "float64",
            "Baseline partisan margin used for swing.",
            unit="share",
        ),
        Column(
            "special_election_swing",
            "float64",
            "actual_margin - historical_baseline_margin",
            unit="share",
        ),
    ),
)

RELIGION = TableSchema(
    name="religion",
    description="State religious composition by survey vintage (Pew Religious Landscape Study). Shares 0-1.",
    frequency="occasional (2007, 2014, 2023-24)",
    key=("state", "survey_year"),
    columns=_STATE_COLS
    + (
        Column("survey_year", "int64", "", nullable=False),
        _pct("pct_christian", ""),
        _pct("pct_evangelical_protestant", ""),
        _pct("pct_mainline_protestant", ""),
        _pct("pct_historically_black_protestant", ""),
        _pct("pct_catholic", ""),
        _pct("pct_mormon", ""),
        _pct("pct_jewish", ""),
        _pct("pct_muslim", ""),
        _pct("pct_other_religion", ""),
        _pct("pct_religiously_unaffiliated", ""),
        _pct("pct_atheist", ""),
        _pct("pct_agnostic", ""),
        _pct("pct_religion_very_important", ""),
        _pct("pct_attend_weekly", ""),
        _pct("pct_pray_daily", ""),
        _pct("pct_highly_religious", ""),
    ),
)

NAEP = TableSchema(
    name="naep",
    description="State NAEP average scale scores and achievement-level shares by assessment year, grade and subject.",
    frequency="biennial (assessment years)",
    key=("state", "assessment_year", "grade", "subject"),
    columns=_STATE_COLS
    + (
        Column("assessment_year", "int64", "", nullable=False),
        Column("grade", "int64", "4 | 8", nullable=False),
        Column("subject", "string", "mathematics | reading", nullable=False),
        Column(
            "average_score", "float64", "Average scale score (0-500 scale).", unit="scale score"
        ),
        _pct("pct_at_or_above_basic", ""),
        _pct("pct_at_or_above_proficient", ""),
        _pct("pct_advanced", ""),
    ),
)

INDIVIDUAL_TURNOUT_CPS = TableSchema(
    name="individual_turnout_cps",
    description="Respondent-level CPS Voting and Registration Supplement records.",
    frequency="biennial (November supplement)",
    key=("respondent_id", "year"),
    columns=(
        Column("respondent_id", "string", "", nullable=False),
        Column("year", "int64", "", nullable=False),
        Column("state", "string", ""),
        Column("state_fips", "string", ""),
        Column("age", "float64", ""),
        Column("sex", "string", ""),
        Column("race", "string", ""),
        Column("hispanic", "bool", ""),
        Column("education", "string", ""),
        Column("income", "string", "Family income bracket."),
        Column("registered", "bool", ""),
        Column("voted", "bool", ""),
        Column("weight", "float64", "Supplement final weight."),
    ),
)

INDIVIDUAL_BEHAVIOR_ANES = TableSchema(
    name="individual_behavior_anes",
    description="Respondent-level ANES Time Series records.",
    frequency="biennial/quadrennial",
    key=("respondent_id", "year"),
    columns=(
        Column("respondent_id", "string", "", nullable=False),
        Column("year", "int64", "", nullable=False),
        Column("state", "string", ""),
        Column("state_fips", "string", ""),
        Column("age", "float64", ""),
        Column("sex", "string", ""),
        Column("race", "string", ""),
        Column("education", "string", ""),
        Column("income", "string", ""),
        Column("religion", "string", ""),
        Column("party_id", "string", "7-point party identification."),
        Column("ideology", "string", ""),
        Column("presidential_vote_choice", "string", ""),
        Column("house_vote_choice", "string", ""),
        Column("senate_vote_choice", "string", ""),
        Column("weight", "float64", ""),
    ),
)

SCHEMAS: dict[str, TableSchema] = {
    s.name: s
    for s in (
        ELECTION_RESULTS,
        ELECTION_RACE_SUMMARY,
        TURNOUT,
        DEMOGRAPHICS,
        POPULATION,
        GEOGRAPHY,
        URBAN_RURAL,
        MIGRATION_FLOWS,
        LABOR,
        INDUSTRY,
        STATE_ECONOMY,
        NATIONAL_ECONOMY,
        CANDIDATES,
        CANDIDATE_FINANCE,
        POLLS,
        APPROVAL_POLLS,
        GENERIC_BALLOT_POLLS,
        SPECIAL_ELECTIONS,
        RELIGION,
        NAEP,
        INDIVIDUAL_TURNOUT_CPS,
        INDIVIDUAL_BEHAVIOR_ANES,
    )
}


def get_schema(table: str) -> TableSchema:
    try:
        return SCHEMAS[table]
    except KeyError as exc:
        raise NormalizationError(f"unknown table schema: {table}") from exc


# ----------------------------------------------------------------- casting

_PANDAS_DTYPES = {
    "string": "string",
    "int64": "Int64",
    "float64": "Float64",
    "bool": "boolean",
}


def _cast_column(series: pd.Series, dtype: str) -> pd.Series:
    if dtype in ("date", "timestamp"):
        out = pd.to_datetime(series, errors="coerce")
        if dtype == "date":
            return out.dt.normalize()
        return out
    if dtype == "int64":
        num = pd.to_numeric(series, errors="coerce")
        return num.round().astype("Int64")
    if dtype == "float64":
        return pd.to_numeric(series, errors="coerce").astype("Float64")
    if dtype == "bool":
        if series.dtype == object or str(series.dtype) == "string":
            mapped = series.map(
                lambda v: (
                    None
                    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA
                    else str(v).strip().lower() in {"true", "1", "t", "yes", "y"}
                )
            )
            return mapped.astype("boolean")
        return series.astype("boolean")
    return series.astype("string")


def enforce_schema(df: pd.DataFrame, schema: TableSchema, *, strict: bool = True) -> pd.DataFrame:
    """Coerce ``df`` to ``schema``.

    * missing nullable columns are added as nulls
    * missing non-nullable columns raise :class:`NormalizationError` when ``strict``
    * extra columns are dropped (they belong in staging, not processed)
    * dtypes are cast with pandas nullable dtypes
    """
    out = df.copy()
    missing_required = [
        c.name for c in schema.all_columns if not c.nullable and c.name not in out.columns
    ]
    if missing_required and strict:
        raise NormalizationError(
            f"table {schema.name!r} is missing required columns: {missing_required}"
        )
    for col in schema.all_columns:
        if col.name not in out.columns:
            out[col.name] = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
        out[col.name] = _cast_column(out[col.name], col.dtype)
    ordered = [c.name for c in schema.all_columns]
    return out[ordered].reset_index(drop=True)


def empty_frame(schema: TableSchema) -> pd.DataFrame:
    return enforce_schema(pd.DataFrame(columns=schema.column_names), schema, strict=False)
