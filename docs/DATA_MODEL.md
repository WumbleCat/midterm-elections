# Data model

Canonical tables live under `data/processed/{table}/` as Parquet (one file per contributing
dataset) and are exposed as DuckDB views of the same name. Every ingested table carries the
provenance columns listed at the end; derived tables are produced by `electiondata transform`
or by feature builds.

## Conventions

* Geography: `state` is the USPS abbreviation, `state_fips` the two-digit code, both from the
  canonical table in `electiondata.geo`. Race-level tables carry `district` (`statewide`,
  `at-large` or a zero-padded number). `US` marks national rows where applicable.
* Shares are stored as **0–1** unless the unit says `percent 0-100` (BLS unemployment rates
  are kept in published units).
* Counts are floats (`Float64`, nullable); years are `Int64`; dates are `datetime64`.
* Parties: `party` ∈ {DEM, REP, LIB, GRN, IND, OTHER}; the original label is in `party_raw`.
* Frequencies are never mixed inside a table: monthly (`labor`, `national_economy`), annual
  (`population`, `industry`, `state_economy`, `demographics`), biennial event (`turnout`,
  `naep`), event (`election_results`, polls), decennial (`urban_rural`), occasional
  (`religion`).
* Natural keys are enforced (duplicates are dropped on ingest and flagged by validation).

## Relationships

```
election_results ──(race_summary)──► election_race_summary ──► features
turnout ───────────┐                                             ▲
population ────────┤ (state, year / date, as_of)  ───────────────┤
geography, urban_rural, demographics, labor, industry,           │
state_economy, national_economy, candidates, candidate_finance,  │
polls, approval_polls, generic_ballot_polls, special_elections,  │
naep, religion ──────────────────────────────────────────────────┘
ingestion_runs (manifest) ◄── every row's ingestion_run_id
```

The feature dataset key is `(state, year, office[, district])`; each family joins on `state`
(or `state, district` for House) after its own point-in-time cut.

<!-- BEGIN GENERATED:data_model -->
_Generated 2026-09-20 from `electiondata.quality.schemas`. Run `electiondata docs` to refresh._

### `election_results`

Candidate-level general-election returns for federal offices (one row per candidate per race).

* **Frequency:** event (election)
* **Natural key:** `state, year, office, district, candidate, party_raw, special`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | Election year. |
| `election_date` | date | yes |  | Date of the general election. |
| `office` | string | no |  | president | senate | house. |
| `district` | string | no |  | 'statewide' for president/senate; zero-padded district number for house. |
| `election_type` | string | no |  | general | special | primary | runoff. |
| `special` | bool | no |  | True for special elections. |
| `candidate` | string | yes |  | Candidate name as reported (upper case). |
| `party_raw` | string | yes |  | Party label exactly as reported by the source. |
| `party` | string | no |  | Canonical party: DEM | REP | LIB | GRN | IND | OTHER. |
| `writein` | bool | yes |  | Write-in candidate flag. |
| `votes` | float64 | yes | votes | Votes received by the candidate (summed over vote modes). |
| `total_votes` | float64 | yes | votes | Total votes cast in the race as reported by the source. |
| `unofficial` | bool | yes |  | Source flagged the result as unofficial. |

### `election_race_summary`

Race-level outcomes derived from election_results (Democratic/Republican/other totals, shares, margin, winner).

* **Frequency:** event (election)
* **Natural key:** `state, year, office, district, special`
* **Kind:** derived (transform output)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  |  |
| `election_date` | date | yes |  |  |
| `office` | string | no |  |  |
| `district` | string | no |  |  |
| `special` | bool | no |  |  |
| `dem_votes` | float64 | yes | votes |  |
| `rep_votes` | float64 | yes | votes |  |
| `other_votes` | float64 | yes | votes |  |
| `total_candidate_votes` | float64 | yes | votes | dem + rep + other |
| `total_votes` | float64 | yes | votes | Total votes reported by the source. |
| `dem_vote_share` | float64 | yes | share 0-1 | dem_votes / total_candidate_votes |
| `rep_vote_share` | float64 | yes | share 0-1 | rep_votes / total_candidate_votes |
| `other_vote_share` | float64 | yes | share 0-1 | other_votes / total_candidate_votes |
| `dem_two_party_share` | float64 | yes | share 0-1 | dem_votes / (dem_votes + rep_votes) |
| `rep_two_party_share` | float64 | yes | share 0-1 | rep_votes / (dem_votes + rep_votes) |
| `dem_rep_margin` | float64 | yes | share -1..1 | dem_two_party_share - rep_two_party_share |
| `winner_party` | string | yes |  | Party of the candidate with the most votes. |
| `winning_margin` | float64 | yes | share | Winner share minus runner-up share (of candidate votes). |
| `dem_candidate` | string | yes |  | Top Democratic candidate. |
| `rep_candidate` | string | yes |  | Top Republican candidate. |
| `n_candidates` | int64 | yes |  | Number of candidates with votes. |
| `uncontested` | bool | yes |  | True when only one of DEM/REP fielded a candidate. |

### `turnout`

State-level registration and ballots cast (EAVS, aggregated from jurisdictions).

* **Frequency:** biennial (federal general elections)
* **Natural key:** `state, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | Election year. |
| `registered_voters` | float64 | yes | persons | Total registered voters (EAVS A1a). |
| `active_registered_voters` | float64 | yes | persons | Active registrations (A1b). |
| `inactive_registered_voters` | float64 | yes | persons | Inactive registrations (A1c). |
| `citizen_voting_age_population` | float64 | yes | persons | CVAP; null unless joined from ACS. |
| `voting_age_population` | float64 | yes | persons | VAP; null unless joined from PEP age tables. |
| `ballots_cast` | float64 | yes | ballots | Total ballots counted / voters who participated (F1a). |
| `in_person_election_day_votes` | float64 | yes | ballots | F1b |
| `early_votes` | float64 | yes | ballots | In-person early votes (F1c). |
| `mail_votes` | float64 | yes | ballots | Mail ballots counted (F1d). |
| `provisional_votes` | float64 | yes | ballots | Provisional ballots counted (F1e). |
| `uocava_votes` | float64 | yes | ballots | UOCAVA ballots counted (F1f). |
| `mail_ballots_transmitted` | float64 | yes | ballots | Mail ballots sent (C1a). |
| `mail_ballots_returned` | float64 | yes | ballots | Mail ballots returned (C1b). |
| `mail_ballots_rejected` | float64 | yes | ballots | Mail ballots rejected (C4a where present). |
| `provisional_ballots_submitted` | float64 | yes | ballots | E1a |
| `n_jurisdictions` | int64 | yes |  | Jurisdictions aggregated. |
| `n_jurisdictions_missing_ballots` | int64 | yes |  | Jurisdictions with no usable ballots_cast value. |

### `demographics`

State-year demographic profile (ACS). One row per state × survey year × survey product. Shares are 0-1.

* **Frequency:** annual (ACS 1-year); 5-year product stored separately by `survey`
* **Natural key:** `state, year, survey`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | ACS reference year. |
| `survey` | string | no |  | acs1 | acs5 |
| `total_population` | float64 | yes | persons |  |
| `median_age` | float64 | yes | years |  |
| `pct_under_18` | float64 | yes | share 0-1 |  |
| `pct_18_24` | float64 | yes | share 0-1 |  |
| `pct_25_34` | float64 | yes | share 0-1 |  |
| `pct_35_44` | float64 | yes | share 0-1 |  |
| `pct_45_54` | float64 | yes | share 0-1 |  |
| `pct_55_64` | float64 | yes | share 0-1 |  |
| `pct_65_74` | float64 | yes | share 0-1 |  |
| `pct_75_plus` | float64 | yes | share 0-1 |  |
| `pct_65_plus` | float64 | yes | share 0-1 |  |
| `pct_male` | float64 | yes | share 0-1 |  |
| `pct_female` | float64 | yes | share 0-1 |  |
| `pct_less_than_high_school` | float64 | yes | share 0-1 | Population 25+. |
| `pct_high_school` | float64 | yes | share 0-1 |  |
| `pct_some_college` | float64 | yes | share 0-1 |  |
| `pct_associate_degree` | float64 | yes | share 0-1 |  |
| `pct_bachelors` | float64 | yes | share 0-1 |  |
| `pct_graduate_degree` | float64 | yes | share 0-1 |  |
| `pct_bachelors_or_higher` | float64 | yes | share 0-1 |  |
| `pct_high_school_or_higher` | float64 | yes | share 0-1 |  |
| `median_household_income` | float64 | yes | USD (current) |  |
| `mean_household_income` | float64 | yes | USD (current) |  |
| `per_capita_income` | float64 | yes | USD (current) |  |
| `gini_coefficient` | float64 | yes | 0-1 |  |
| `poverty_rate` | float64 | yes | share 0-1 | Population below poverty level / population for whom poverty status is determined. |
| `pct_white` | float64 | yes | share 0-1 |  |
| `pct_white_non_hispanic` | float64 | yes | share 0-1 |  |
| `pct_black` | float64 | yes | share 0-1 |  |
| `pct_hispanic_latino` | float64 | yes | share 0-1 |  |
| `pct_asian` | float64 | yes | share 0-1 |  |
| `pct_native_american` | float64 | yes | share 0-1 |  |
| `pct_native_hawaiian_pacific_islander` | float64 | yes | share 0-1 |  |
| `pct_multiracial` | float64 | yes | share 0-1 |  |
| `pct_other_race` | float64 | yes | share 0-1 |  |
| `pct_foreign_born` | float64 | yes | share 0-1 |  |
| `pct_naturalized_citizen` | float64 | yes | share 0-1 |  |
| `pct_non_citizen` | float64 | yes | share 0-1 |  |
| `pct_native_born` | float64 | yes | share 0-1 |  |
| `citizen_voting_age_population` | float64 | yes | persons | Citizens 18+ (B05003). |

### `population`

Annual state population estimates and components of change (Census PEP). Each vintage is stored separately.

* **Frequency:** annual (July 1 estimates)
* **Natural key:** `state, year, revision_vintage`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | Estimate year (July 1). |
| `population` | float64 | yes | persons |  |
| `births` | float64 | yes | persons |  |
| `deaths` | float64 | yes | persons |  |
| `natural_change` | float64 | yes | persons (net) |  |
| `international_migration` | float64 | yes | persons (net) | Net international migration. |
| `domestic_migration` | float64 | yes | persons (net) | Net domestic migration. |
| `net_migration` | float64 | yes | persons (net) | Net migration (international + domestic). |
| `domestic_migration_rate` | float64 | yes | per 1000 | Per 1,000 population (PEP RDOMESTICMIG). |
| `net_migration_rate` | float64 | yes | per 1000 | Per 1,000 population (PEP RNETMIG). |

### `geography`

State land/water area from Census Gazetteer files (used for population density).

* **Frequency:** annual (Gazetteer vintage)
* **Natural key:** `state, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | Gazetteer vintage year. |
| `land_area_sq_miles` | float64 | yes | sq mi |  |
| `water_area_sq_miles` | float64 | yes | sq mi |  |

### `urban_rural`

Urban/rural population by state from decennial census classifications (not annual).

* **Frequency:** decennial
* **Natural key:** `state, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  | Census year of the classification. |
| `total_population` | float64 | yes | persons |  |
| `urban_population` | float64 | yes | persons |  |
| `rural_population` | float64 | yes | persons |  |
| `pct_urban` | float64 | yes | share 0-1 |  |
| `pct_rural` | float64 | yes | share 0-1 |  |

### `migration_flows`

State-to-state migration flows (ACS). One row per origin × destination × year.

* **Frequency:** annual (ACS 1-year)
* **Natural key:** `origin_state, destination_state, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `origin_state` | string | no |  | USPS abbr of prior residence. |
| `destination_state` | string | no |  | USPS abbr of current residence. |
| `year` | int64 | no |  |  |
| `movers` | float64 | yes | persons | Estimated persons who moved. |
| `movers_moe` | float64 | yes | persons | Margin of error. |

### `labor`

Monthly state labour-market series (BLS LAUS). Values are the vintage current at retrieval; the API does not expose historical revisions.

* **Frequency:** monthly
* **Natural key:** `state, date, seasonally_adjusted`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)
* **Note:** unemployment_rate is stored in BLS units (percent 0-100), not a 0-1 share.

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `date` | date | no |  | First day of the reference month. |
| `seasonally_adjusted` | bool | no |  |  |
| `labor_force` | float64 | yes | persons |  |
| `employment` | float64 | yes | persons |  |
| `unemployment` | float64 | yes | persons |  |
| `unemployment_rate` | float64 | yes | percent 0-100 | Percent (0-100) as published by BLS. |

### `industry`

Annual state employment, wages and establishments by industry (BLS QCEW annual averages).

* **Frequency:** annual
* **Natural key:** `state, year, industry_code, own_code`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  |  |
| `industry_code` | string | no |  | QCEW industry code (10 = total, NAICS supersectors, sectors). |
| `own_code` | string | no |  | Ownership code (0 = total covered, 5 = private, 1-3 = government). |
| `agglvl_code` | string | yes |  | QCEW aggregation level code. |
| `annual_avg_establishments` | float64 | yes | establishments |  |
| `annual_avg_employment` | float64 | yes | persons |  |
| `total_annual_wages` | float64 | yes | USD |  |
| `annual_avg_weekly_wage` | float64 | yes | USD |  |
| `avg_annual_pay` | float64 | yes | USD |  |

### `state_economy`

Annual state GDP, personal income and regional price parities (BEA Regional Accounts).

* **Frequency:** annual
* **Natural key:** `state, year, measure`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `year` | int64 | no |  |  |
| `measure` | string | no |  | real_gdp | nominal_gdp | personal_income | per_capita_personal_income | regional_price_parity | real_personal_income | ... |
| `value` | float64 | yes |  |  |
| `unit` | string | yes |  | Unit as published by BEA (e.g. millions of chained 2017 dollars). |
| `bea_table` | string | yes |  | BEA table name (SAGDP9N, SAINC1, SARPP, ...). |
| `line_code` | string | yes |  | BEA line code. |

### `national_economy`

Monthly national series (BLS CPI, CES payrolls/earnings, CPS unemployment & participation). Long format.

* **Frequency:** monthly
* **Natural key:** `date, series_id`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `date` | date | no |  | First day of the reference month. |
| `series_id` | string | no |  | BLS series id. |
| `measure` | string | no |  | cpi_all_items | cpi_core | nonfarm_payrolls | average_hourly_earnings | unemployment_rate | labor_force_participation_rate |
| `value` | float64 | yes |  |  |
| `seasonally_adjusted` | bool | yes |  |  |
| `unit` | string | yes |  | index 1982-84=100 | thousands | USD | percent |

### `candidates`

Candidate identity and incumbency (FEC candidate master, one row per candidate × cycle).

* **Frequency:** continuous (bulk file refreshed by FEC); snapshot per retrieval
* **Natural key:** `candidate_id, cycle`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `candidate_id` | string | no |  | FEC candidate id. |
| `cycle` | int64 | no |  | Two-year election cycle (file year). |
| `election_year` | int64 | yes |  | Year of the candidate's election (FEC CAND_ELECTION_YR). |
| `name` | string | yes |  |  |
| `party_raw` | string | yes |  | FEC party code. |
| `party` | string | yes |  | Canonical party. |
| `office` | string | yes |  | president | senate | house |
| `state` | string | yes |  | USPS abbr; 'US' for president. |
| `state_fips` | string | yes |  |  |
| `district` | string | yes |  | Zero-padded district; 'statewide' for senate; '00' style raw preserved in district_raw. |
| `district_raw` | string | yes |  |  |
| `incumbent_challenger_status` | string | yes |  | I = incumbent, C = challenger, O = open seat. |
| `candidate_status` | string | yes |  | C = statutory candidate, F = future, N = not yet, P = prior. |
| `principal_committee_id` | string | yes |  |  |

### `candidate_finance`

Candidate financial summaries (FEC 'all candidates' summary file). coverage_end_date is the reporting period end; publication_date approximates the filing deadline.

* **Frequency:** per report (snapshot files refreshed by FEC)
* **Natural key:** `candidate_id, cycle, coverage_end_date, revision_vintage`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `candidate_id` | string | no |  |  |
| `cycle` | int64 | no |  |  |
| `name` | string | yes |  |  |
| `party_raw` | string | yes |  |  |
| `party` | string | yes |  |  |
| `office` | string | yes |  |  |
| `state` | string | yes |  |  |
| `state_fips` | string | yes |  |  |
| `district` | string | yes |  |  |
| `incumbent_challenger_status` | string | yes |  |  |
| `coverage_end_date` | date | no |  | End of the period covered by the totals. |
| `total_receipts` | float64 | yes | USD |  |
| `transfers_from_authorized` | float64 | yes | USD |  |
| `total_disbursements` | float64 | yes | USD |  |
| `transfers_to_authorized` | float64 | yes | USD |  |
| `cash_on_hand_beginning` | float64 | yes | USD |  |
| `cash_on_hand_end` | float64 | yes | USD |  |
| `candidate_contributions` | float64 | yes | USD | Self-financing contributions. |
| `candidate_loans` | float64 | yes | USD |  |
| `other_loans` | float64 | yes | USD |  |
| `candidate_loan_repayments` | float64 | yes | USD |  |
| `other_loan_repayments` | float64 | yes | USD |  |
| `debts_owed_by` | float64 | yes | USD |  |
| `individual_contributions` | float64 | yes | USD |  |
| `other_committee_contributions` | float64 | yes | USD | PAC contributions. |
| `party_contributions` | float64 | yes | USD |  |
| `refunds_individual` | float64 | yes | USD |  |
| `refunds_committee` | float64 | yes | USD |  |

### `polls`

Race-specific poll observations (one row per poll × race). Populated via the manual CSV adapter until a durable structured source is chosen.

* **Frequency:** event (poll)
* **Natural key:** `poll_id, state, office, district, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `poll_id` | string | no |  |  |
| `state` | string | no |  |  |
| `state_fips` | string | yes |  |  |
| `district` | string | yes |  | 'statewide' or district number. |
| `office` | string | no |  |  |
| `year` | int64 | no |  | Election year. |
| `pollster` | string | yes |  |  |
| `pollster_grade` | string | yes |  |  |
| `sponsor` | string | yes |  |  |
| `start_date` | date | yes |  | Field start. |
| `end_date` | date | yes |  | Field end. |
| `sample_size` | float64 | yes |  |  |
| `population_type` | string | yes |  | lv | rv | a |
| `mode` | string | yes |  |  |
| `dem_candidate` | string | yes |  |  |
| `rep_candidate` | string | yes |  |  |
| `dem_pct` | float64 | yes | share 0-1 | Democratic share as 0-1. |
| `rep_pct` | float64 | yes | share 0-1 |  |
| `other_pct` | float64 | yes | share 0-1 |  |
| `undecided_pct` | float64 | yes | share 0-1 |  |
| `poll_margin` | float64 | yes | share | dem_pct - rep_pct |

### `approval_polls`

Presidential approval poll observations.

* **Frequency:** event (poll)
* **Natural key:** `poll_id`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `poll_id` | string | no |  |  |
| `pollster` | string | yes |  |  |
| `president` | string | yes |  |  |
| `start_date` | date | yes |  |  |
| `end_date` | date | yes |  |  |
| `sample_size` | float64 | yes |  |  |
| `population_type` | string | yes |  |  |
| `approve` | float64 | yes | share 0-1 |  |
| `disapprove` | float64 | yes | share 0-1 |  |
| `net_approval` | float64 | yes | share | approve - disapprove |

### `generic_ballot_polls`

Generic congressional ballot poll observations.

* **Frequency:** event (poll)
* **Natural key:** `poll_id`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `poll_id` | string | no |  |  |
| `pollster` | string | yes |  |  |
| `start_date` | date | yes |  |  |
| `end_date` | date | yes |  |  |
| `sample_size` | float64 | yes |  |  |
| `population_type` | string | yes |  |  |
| `generic_dem` | float64 | yes | share 0-1 |  |
| `generic_rep` | float64 | yes | share 0-1 |  |
| `generic_other` | float64 | yes | share 0-1 |  |
| `undecided` | float64 | yes | share 0-1 |  |
| `generic_margin` | float64 | yes | share | generic_dem - generic_rep |

### `special_elections`

Special-election results with a partisan baseline for swing computation.

* **Frequency:** event
* **Natural key:** `state, district, office, election_date`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  |  |
| `state_fips` | string | yes |  |  |
| `district` | string | yes |  |  |
| `office` | string | no |  |  |
| `election_date` | date | no |  |  |
| `dem_vote_share` | float64 | yes | share 0-1 |  |
| `rep_vote_share` | float64 | yes | share 0-1 |  |
| `actual_margin` | float64 | yes | share | dem - rep |
| `historical_baseline_margin` | float64 | yes | share | Baseline partisan margin used for swing. |
| `special_election_swing` | float64 | yes | share | actual_margin - historical_baseline_margin |

### `religion`

State religious composition by survey vintage (Pew Religious Landscape Study). Shares 0-1.

* **Frequency:** occasional (2007, 2014, 2023-24)
* **Natural key:** `state, survey_year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `survey_year` | int64 | no |  |  |
| `pct_christian` | float64 | yes | share 0-1 |  |
| `pct_evangelical_protestant` | float64 | yes | share 0-1 |  |
| `pct_mainline_protestant` | float64 | yes | share 0-1 |  |
| `pct_historically_black_protestant` | float64 | yes | share 0-1 |  |
| `pct_catholic` | float64 | yes | share 0-1 |  |
| `pct_mormon` | float64 | yes | share 0-1 |  |
| `pct_jewish` | float64 | yes | share 0-1 |  |
| `pct_muslim` | float64 | yes | share 0-1 |  |
| `pct_other_religion` | float64 | yes | share 0-1 |  |
| `pct_religiously_unaffiliated` | float64 | yes | share 0-1 |  |
| `pct_atheist` | float64 | yes | share 0-1 |  |
| `pct_agnostic` | float64 | yes | share 0-1 |  |
| `pct_religion_very_important` | float64 | yes | share 0-1 |  |
| `pct_attend_weekly` | float64 | yes | share 0-1 |  |
| `pct_pray_daily` | float64 | yes | share 0-1 |  |
| `pct_highly_religious` | float64 | yes | share 0-1 |  |

### `naep`

State NAEP average scale scores and achievement-level shares by assessment year, grade and subject.

* **Frequency:** biennial (assessment years)
* **Natural key:** `state, assessment_year, grade, subject`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `state` | string | no |  | USPS state abbreviation (canonical). |
| `state_fips` | string | no |  | Two-digit state FIPS code. |
| `assessment_year` | int64 | no |  |  |
| `grade` | int64 | no |  | 4 | 8 |
| `subject` | string | no |  | mathematics | reading |
| `average_score` | float64 | yes | scale score | Average scale score (0-500 scale). |
| `pct_at_or_above_basic` | float64 | yes | share 0-1 |  |
| `pct_at_or_above_proficient` | float64 | yes | share 0-1 |  |
| `pct_advanced` | float64 | yes | share 0-1 |  |

### `individual_turnout_cps`

Respondent-level CPS Voting and Registration Supplement records.

* **Frequency:** biennial (November supplement)
* **Natural key:** `respondent_id, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `respondent_id` | string | no |  |  |
| `year` | int64 | no |  |  |
| `state` | string | yes |  |  |
| `state_fips` | string | yes |  |  |
| `age` | float64 | yes |  |  |
| `sex` | string | yes |  |  |
| `race` | string | yes |  |  |
| `hispanic` | bool | yes |  |  |
| `education` | string | yes |  |  |
| `income` | string | yes |  | Family income bracket. |
| `registered` | bool | yes |  |  |
| `voted` | bool | yes |  |  |
| `weight` | float64 | yes |  | Supplement final weight. |

### `individual_behavior_anes`

Respondent-level ANES Time Series records.

* **Frequency:** biennial/quadrennial
* **Natural key:** `respondent_id, year`
* **Kind:** ingested (normalized)
* **Provenance columns:** yes (see below)

| Column | Type | Nullable | Unit | Description |
|---|---|---|---|---|
| `respondent_id` | string | no |  |  |
| `year` | int64 | no |  |  |
| `state` | string | yes |  |  |
| `state_fips` | string | yes |  |  |
| `age` | float64 | yes |  |  |
| `sex` | string | yes |  |  |
| `race` | string | yes |  |  |
| `education` | string | yes |  |  |
| `income` | string | yes |  |  |
| `religion` | string | yes |  |  |
| `party_id` | string | yes |  | 7-point party identification. |
| `ideology` | string | yes |  |  |
| `presidential_vote_choice` | string | yes |  |  |
| `house_vote_choice` | string | yes |  |  |
| `senate_vote_choice` | string | yes |  |  |
| `weight` | float64 | yes |  |  |

### Provenance columns (every ingested table)

| Column | Type | Nullable | Description |
|---|---|---|---|
| `observation_date` | date | yes | Date the observation refers to (period end for spans). |
| `period_start` | date | yes | Start of the reference period, if the observation spans one. |
| `period_end` | date | yes | End of the reference period. |
| `publication_date` | date | yes | Date the value became publicly available. Rows with publication_date > as_of are excluded by point-in-time filters. |
| `publication_date_estimated` | bool | no | True when publication_date comes from a documented release-lag rule rather than a recorded release date. |
| `retrieval_date` | date | no | Date the raw file was downloaded. |
| `source` | string | no | Short source id (MEDSL, BLS, ...). |
| `source_url` | string | yes | URL of the raw artifact (credentials redacted). |
| `dataset_id` | string | no | Registry dataset id that produced the row. |
| `revision_vintage` | string | yes | Vintage/version of the upstream release (e.g. PEP vintage, MEDSL version). |
| `ingestion_run_id` | string | no | Manifest run id. |
<!-- END GENERATED:data_model -->

## Feature dataset

`data/features/{office}_{year}_asof_{date}.parquet` — one row per race; columns are listed in
`docs/PACKAGE_API.md`. The JSON sidecar records, per family, availability, row counts, max
publication date, share of estimated publication dates, dataset ids and ingestion runs, plus
overall missingness.
