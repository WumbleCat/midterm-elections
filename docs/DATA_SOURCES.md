# Data sources

The registry (`src/electiondata/ingestion/registry.py`) is the single source of truth for
source metadata and implementation status; the generated section below is rendered from it
with `electiondata docs`. Hand-written notes (access findings, manual templates) follow it.

<!-- BEGIN GENERATED:data_sources -->
_Generated 2026-09-20 from the source registry. Hand-written notes live outside the markers._

### U.S. Election Assistance Commission — Election Administration and Voting Survey (EAVS)

* **Dataset id:** `eac-eavs` (phase 1)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.eac.gov/research-and-data/datasets-codebooks-and-surveys
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** biennial; jurisdiction -> aggregated to state
* **Update frequency:** Published ~June of the year after the election; revised versions later.
* **Raw table:** `eavs_raw` → **normalized table:** `turnout`
* **Variables:** `A1a`, `A1b`, `A1c`, `C1a`, `C1b`, `E1a`, `F1a`, `F1b`, `F1c`, `F1d`, `F1e`, `F1f`
* **Ingest options:** `years`: comma-separated EAVS years to ingest (default: 2020,2022,2024)
* **Description:** Registration, ballots cast, mail/early/provisional voting by jurisdiction; aggregated to state level.
* **Known limitations:** Only 2020, 2022 and 2024 public-release CSVs have stable URLs and a consistent item numbering; earlier years use different variable names. Negative EAVS codes (-88/-99 etc.) are treated as missing. Jurisdiction non-response is reported in n_jurisdictions_missing_ballots.

### Federal Election Commission — Federal Elections official results (Excel)

* **Dataset id:** `fec-election-results` (phase 1)
* **Status:** TODO
* **Authoritative URL:** https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/
* **Access method:** download_table
* **Credentials:** none
* **Frequency / geography:** event (biennial); state / district
* **Update frequency:** Once per election, ~12 months after election day.
* **Raw table:** `fec_election_results_raw` → **normalized table:** `election_results`
* **Variables:** `STATE`, `CANDIDATE NAME`, `PARTY`, `GENERAL VOTES`, `GENERAL %`, `GE WINNER INDICATOR`
* **Description:** Official certified federal results published by the FEC as multi-sheet Excel workbooks (federalelections{year}.xlsx).
* **Known limitations:** Workbook layouts differ by year (sheet names, header rows, footnotes); parser not yet written. Files verified reachable at https://www.fec.gov/resources/cms-content/documents/federalelections{year}.xlsx for 2020/2022.

### MIT Election Data + Science Lab — U.S. House returns 1976-2024

* **Dataset id:** `medsl-house` (phase 1)
* **Status:** MANUAL — tested with fixtures
* **Authoritative URL:** https://doi.org/10.7910/DVN/IG0UN2
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** event (biennial); congressional_district
* **Update frequency:** MEDSL republishes after each federal election.
* **Raw table:** `medsl_house_raw` → **normalized table:** `election_results`
* **Variables:** `year`, `state`, `district`, `candidate`, `party`, `candidatevotes`, `totalvotes`, `runoff`, `special`, `fusion_ticket`
* **Description:** District-level House returns by candidate, cleaned by MEDSL. The Dataverse file is behind a guestbook (terms acknowledgement) that the API refuses, so download 1976-2024-house.tab in a browser and place it in data/raw/medsl/medsl-house/manual/.
* **Known limitations:** Guestbook-gated download (API returns 'You may not download this file without the required Guestbook response'). Parser is fixture-tested on the documented 1976-2024 layout; vote 'mode' rows are collapsed (TOTAL preferred, otherwise summed) and runoff rows are excluded.

### MIT Election Data + Science Lab — Presidential returns by state 1976-2024

* **Dataset id:** `medsl-president` (phase 1)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://doi.org/10.7910/DVN/42MVDX
* **Access method:** standardized_dataset
* **Credentials:** none
* **Frequency / geography:** event (quadrennial); state
* **Update frequency:** MEDSL republishes after each presidential election.
* **Raw table:** `medsl_president_raw` → **normalized table:** `election_results`
* **Variables:** `year`, `state`, `candidate`, `party_detailed`, `party_simplified`, `candidatevotes`, `totalvotes`, `writein`
* **Description:** State-level presidential returns by candidate, cleaned by MEDSL.
* **Known limitations:** Some states report fusion/ballot-line splits; votes are summed per candidate and party assigned from the largest line.

### MIT Election Data + Science Lab — U.S. Senate returns 1976-2024

* **Dataset id:** `medsl-senate` (phase 1)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://doi.org/10.7910/DVN/PEJ5QU
* **Access method:** standardized_dataset
* **Credentials:** none
* **Frequency / geography:** event (biennial); state
* **Update frequency:** MEDSL republishes after each federal election (months later).
* **Raw table:** `medsl_senate_raw` → **normalized table:** `election_results`
* **Variables:** `year`, `state`, `office`, `candidate`, `party_detailed`, `party_simplified`, `candidatevotes`, `totalvotes`, `special`, `stage`
* **Description:** Candidate-level general-election Senate returns, cleaned by MEDSL, from Harvard Dataverse.
* **Known limitations:** General-election stage only; Louisiana jungle primaries and runoffs follow MEDSL conventions. Dataset versions replace earlier ones (revision_vintage = Dataverse version).

### U.S. Census Bureau — American Community Survey — ACS 1-year state profile (age, sex, education, income, inequality, poverty, race/ethnicity, citizenship)

* **Dataset id:** `census-acs-profile` (phase 2)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://api.census.gov/data.html
* **Access method:** api
* **Credentials:** CENSUS_API_KEY
* **Frequency / geography:** annual; state
* **Update frequency:** Annual, mid-September (1-year).
* **Raw table:** `acs_raw` → **normalized table:** `demographics`
* **Variables:** `B01003_001E`, `B01002_001E`, `B01001_*`, `B15003_*`, `B19013_001E`, `B19301_001E`, `B19083_001E`, `B17001_*`, `B03002_*`, `B05002_*`, `B05003_*`
* **Ingest options:** `years`: comma-separated ACS years (default: 2010-latest); `survey`: acs1 (default) or acs5
* **Description:** Detailed tables B01001, B01002, B15003, B19013, B19025/B11001, B19301, B19083, B17001, B03002, B05002, B05003 fetched from the Census API and reduced to one row per state-year.
* **Known limitations:** Requires CENSUS_API_KEY (the API answers HTTP 200 'Missing Key'/'Invalid Key' HTML pages otherwise; a new key is invalid until activated). Verified live 2026-09-20 for 2010-2023 (all variable ids checked against the API metadata); 2020 1-year estimates were not released (experimental only). pct_non_citizen is derived as foreign born minus naturalized because the direct row id changed in 2013.

### U.S. Census Bureau — Gazetteer files — State land and water area

* **Dataset id:** `census-gazetteer` (phase 2)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** annual vintage (slow-moving); state
* **Update frequency:** Annual.
* **Raw table:** `gazetteer_raw` → **normalized table:** `geography`
* **Variables:** `GEOID`, `ALAND_SQMI`, `AWATER_SQMI`
* **Ingest options:** `vintages`: comma-separated Gazetteer years (default 2012,2016,2020,2024)
* **Description:** Land area in square miles for population density (state files for 2024+, county files summed to states for earlier vintages).
* **Known limitations:** -

### U.S. Census Bureau — ACS state-to-state migration flows — State-to-state migration flows

* **Dataset id:** `census-migration-flows` (phase 2)
* **Status:** TODO
* **Authoritative URL:** https://www.census.gov/topics/population/migration/guidance/state-to-state-migration-flows.html
* **Access method:** download_table
* **Credentials:** none
* **Frequency / geography:** annual; state pairs
* **Update frequency:** Annual.
* **Raw table:** `migration_flows_raw` → **normalized table:** `migration_flows`
* **Variables:** -
* **Description:** Origin-destination mover counts published as multi-header Excel tables (State_to_State_Migration_Table_{year}.xlsx).
* **Known limitations:** Excel layout has merged multi-row headers and MOE columns interleaved; parser not written. Net domestic migration is already available from census-pep-population.

### U.S. Census Bureau — Population Estimates Program — State population totals and components of change (vintages 2009, 2019, 2024)

* **Dataset id:** `census-pep-population` (phase 2)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.census.gov/programs-surveys/popest/data/data-sets.html
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** annual; state
* **Update frequency:** New vintage every December.
* **Raw table:** `pep_raw` → **normalized table:** `population`
* **Variables:** `POPESTIMATE*`, `BIRTHS*`, `DEATHS*`, `INTERNATIONALMIG*`, `DOMESTICMIG*`, `NETMIG*`, `RDOMESTICMIG*`, `RNETMIG*`
* **Description:** NST-EST alldata CSVs (2000-2010 intercensal, 2010-2019, 2020-2024) with population, births, deaths and domestic/international migration.
* **Known limitations:** Each vintage revises earlier years; all vintages are kept and distinguished by revision_vintage. The intercensal 2000-2010 file has no migration components in the same layout (population only).

### U.S. Census Bureau — Decennial urban/rural classification — 2020 urban and rural population by county, aggregated to state

* **Dataset id:** `census-urban-rural` (phase 2)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.census.gov/programs-surveys/geography/guidance/geo-areas/urban-rural.html
* **Access method:** download_table
* **Credentials:** none
* **Frequency / geography:** decennial; county -> state
* **Update frequency:** Decennial.
* **Raw table:** `urban_rural_raw` → **normalized table:** `urban_rural`
* **Variables:** `STATE`, `COUNTY`, `POP_COU`, `POP_URB`, `POP_RUR`
* **Description:** 2020_UA_COUNTY.xlsx urban/rural population per county summed to states.
* **Known limitations:** 2020 only; 2010 classification (PctUrbanRural_State.xls) not yet parsed.

### Bureau of Economic Analysis — Regional Economic Accounts — Annual state personal income and per-capita personal income (SAINC1)

* **Dataset id:** `bea-personal-income` (phase 3)
* **Status:** BLOCKED — tested with fixtures
* **Authoritative URL:** https://apps.bea.gov/api/
* **Access method:** api
* **Credentials:** BEA_API_KEY
* **Frequency / geography:** annual; state
* **Update frequency:** Annual.
* **Raw table:** `bea_income_raw` → **normalized table:** `state_economy`
* **Variables:** `personal_income`, `per_capita_personal_income`
* **Description:** BEA Regional API, TableName SAINC1 LineCode 1 (personal income), 2 (population), 3 (per capita).
* **Known limitations:** Requires BEA_API_KEY. Fixture-tested, not yet run live.

### Bureau of Economic Analysis — Regional Price Parities — State regional price parities and real personal income (SARPP, SARPI)

* **Dataset id:** `bea-rpp` (phase 3)
* **Status:** BLOCKED — tested with fixtures
* **Authoritative URL:** https://apps.bea.gov/api/
* **Access method:** api
* **Credentials:** BEA_API_KEY
* **Frequency / geography:** annual; state
* **Update frequency:** Annual (December).
* **Raw table:** `bea_rpp_raw` → **normalized table:** `state_economy`
* **Variables:** `regional_price_parity`, `real_personal_income`, `real_per_capita_personal_income`
* **Description:** BEA Regional API TableName SARPP LineCode 1 (RPP all items) and SARPI LineCode 1/2 (real personal income, real per capita).
* **Known limitations:** Requires BEA_API_KEY. Fixture-tested, not yet run live.

### Bureau of Economic Analysis — Regional Economic Accounts — Annual state real and nominal GDP (SAGDP9N, SAGDP2N)

* **Dataset id:** `bea-state-gdp` (phase 3)
* **Status:** BLOCKED — tested with fixtures
* **Authoritative URL:** https://apps.bea.gov/api/
* **Access method:** api
* **Credentials:** BEA_API_KEY
* **Frequency / geography:** annual; state
* **Update frequency:** Annual (with quarterly updates).
* **Raw table:** `bea_gdp_raw` → **normalized table:** `state_economy`
* **Variables:** `real_gdp`, `nominal_gdp`
* **Description:** BEA Regional API, TableName SAGDP9N (real GDP, chained dollars) and SAGDP2N (current dollars), LineCode 1 (all industries).
* **Known limitations:** Requires BEA_API_KEY (free). Fixture-tested, not yet run live. Current vintage only; comprehensive revisions are not tracked.

### Bureau of Labor Statistics — Current Employment Statistics / CPS — National nonfarm payrolls, average hourly earnings, unemployment rate, participation rate

* **Dataset id:** `bls-ces-national` (phase 3)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.bls.gov/ces/
* **Access method:** api
* **Credentials:** none
* **Frequency / geography:** monthly; nation
* **Update frequency:** Monthly (first Friday).
* **Raw table:** `bls_ces_raw` → **normalized table:** `national_economy`
* **Variables:** `nonfarm_payrolls`, `average_hourly_earnings`, `unemployment_rate`, `labor_force_participation_rate`
* **Ingest options:** `start_year`: first year (default 1996); `end_year`: last year
* **Description:** Series CES0000000001, CES0500000003, LNS14000000, LNS11300000.
* **Known limitations:** Current vintage only; payroll revisions are not tracked. publication_date estimated (month end + 8 days).

### Bureau of Labor Statistics — Consumer Price Index — CPI-U all items and core (national, NSA and SA)

* **Dataset id:** `bls-cpi` (phase 3)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.bls.gov/cpi/
* **Access method:** api
* **Credentials:** none
* **Frequency / geography:** monthly; nation
* **Update frequency:** Monthly.
* **Raw table:** `bls_cpi_raw` → **normalized table:** `national_economy`
* **Variables:** `cpi_all_items`, `cpi_core`
* **Ingest options:** `start_year`: first year (default 1996); `end_year`: last year
* **Description:** Series CUUR0000SA0, CUSR0000SA0, CUUR0000SA0L1E, CUSR0000SA0L1E.
* **Known limitations:** publication_date estimated (month end + 15 days).

### Bureau of Labor Statistics — Local Area Unemployment Statistics — State monthly labour force, employment, unemployment, unemployment rate (seasonally adjusted)

* **Dataset id:** `bls-laus` (phase 3)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.bls.gov/lau/
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** monthly; state
* **Update frequency:** Monthly (~3 weeks after the reference month).
* **Raw table:** `bls_laus_raw` → **normalized table:** `labor`
* **Variables:** `unemployment_rate`, `unemployment`, `employment`, `labor_force`
* **Ingest options:** `mode`: auto (default: bulk when contact email is set) | bulk | api; `start_year`: first year to keep (bulk) / to request (api); `end_year`: last year (api mode)
* **Description:** Official bulk flat file la.data.3.AllStatesS (all states, seasonally adjusted, 1976-present) filtered to series LASST{fips}00000000000{03,04,05,06}; the BLS Public Data API is used instead with option mode=api.
* **Known limitations:** Bulk mode needs ELECTIONDATA_CONTACT_EMAIL because BLS requires an identifying User-Agent on download.bls.gov (403 otherwise). API mode without BLS_API_KEY is limited to 25 series/query, 10 years/query and 25 queries/day. Both return the current vintage only; publication_date is estimated from the release calendar (month end + 21 days) and annual benchmark revisions are not tracked.

### Bureau of Labor Statistics — Quarterly Census of Employment and Wages — State annual employment/wages by industry (QCEW open data)

* **Dataset id:** `bls-qcew` (phase 3)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.bls.gov/cew/additional-resources/open-data/
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** annual; state
* **Update frequency:** Annual averages ~June of the following year.
* **Raw table:** `bls_qcew_raw` → **normalized table:** `industry`
* **Variables:** `annual_avg_emplvl`, `total_annual_wages`, `annual_avg_estabs`, `annual_avg_wkly_wage`, `avg_annual_pay`
* **Ingest options:** `years`: comma-separated years (default: latest 2 available)
* **Description:** Per-industry annual CSV slices (data.bls.gov/cew/data/api/{year}/a/industry/{code}.csv) filtered to state rows for total, supersectors and NAICS sectors.
* **Known limitations:** Default pull covers a small year range (option years). Suppressed cells are null.

### Federal Election Commission — bulk data — All candidates financial summary (weball{yy}.zip) by cycle

* **Dataset id:** `fec-candidate-finance` (phase 4)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.fec.gov/campaign-finance-data/all-candidates-file-description/
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** per report (snapshot per retrieval); state / district
* **Update frequency:** Refreshed nightly during a cycle.
* **Raw table:** `fec_weball_raw` → **normalized table:** `candidate_finance`
* **Variables:** `TTL_RECEIPTS`, `TTL_DISB`, `COH_COP`, `DEBTS_OWED_BY`, `TTL_INDIV_CONTRIB`, `OTHER_POL_CMTE_CONTRIB`, `POL_PTY_CONTRIB`, `CVG_END_DT`
* **Ingest options:** `cycles`: comma-separated even years (default: 2010-current)
* **Description:** Receipts, disbursements, cash on hand, debts and contribution breakdowns per candidate with the coverage end date of the latest report.
* **Known limitations:** Historical cycle files hold the FINAL totals (coverage end 12/31); pre-election snapshots for past cycles are only available via FEC API report filings (todo: fec-committee-reports). Point-in-time filters therefore exclude finance for past elections unless a snapshot retrieved before election day exists.

### Federal Election Commission — bulk data — Candidate master file (cn{yy}.zip) by cycle

* **Dataset id:** `fec-candidate-master` (phase 4)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.fec.gov/campaign-finance-data/candidate-master-file-description/
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** continuous (snapshot per retrieval); state / district
* **Update frequency:** FEC refreshes bulk files nightly; historical cycles are frozen.
* **Raw table:** `fec_cn_raw` → **normalized table:** `candidates`
* **Variables:** `CAND_ID`, `CAND_NAME`, `CAND_PTY_AFFILIATION`, `CAND_ELECTION_YR`, `CAND_OFFICE_ST`, `CAND_OFFICE`, `CAND_OFFICE_DISTRICT`, `CAND_ICI`, `CAND_STATUS`
* **Ingest options:** `cycles`: comma-separated even years (default: 2010-current)
* **Description:** All registered federal candidates with party, office, state, district and incumbent/challenger/open status.
* **Known limitations:** Includes non-serious filers; join with results/finance to select major candidates. Historical cycle files are the final snapshot for that cycle.

### Federal Election Commission — OpenFEC API — Candidate committee periodic reports (pre-election snapshots)

* **Dataset id:** `fec-committee-reports` (phase 4)
* **Status:** TODO
* **Authoritative URL:** https://api.open.fec.gov/developers/
* **Access method:** api
* **Credentials:** FEC_API_KEY
* **Frequency / geography:** per report; state / district
* **Update frequency:** Continuous.
* **Raw table:** `fec_reports_raw` → **normalized table:** `candidate_finance`
* **Variables:** -
* **Description:** /reports/{committee_type}/ filings with coverage_end_date and receipt_date, giving true point-in-time finance for historical backtests.
* **Known limitations:** Not implemented. DEMO_KEY rate limits are low; a registered api.data.gov key is recommended.

### Federal Election Commission — bulk data — Independent expenditures (outside spending)

* **Dataset id:** `fec-independent-expenditures` (phase 4)
* **Status:** DEFERRED
* **Authoritative URL:** https://www.fec.gov/campaign-finance-data/independent-expenditures-file-description/
* **Access method:** bulk_file
* **Credentials:** none
* **Frequency / geography:** per filing; state / district
* **Update frequency:** Continuous.
* **Raw table:** `fec_ie_raw` → **normalized table:** `candidate_finance`
* **Variables:** -
* **Description:** Support/oppose spending by outside groups per candidate.
* **Known limitations:** Deferred: second-stage feature per the specification; bulk files are large and need candidate matching.

### Presidential approval polls (manual CSV adapter) — Presidential approval poll-level observations

* **Dataset id:** `polls-approval` (phase 5)
* **Status:** MANUAL — tested with fixtures
* **Authoritative URL:** https://news.gallup.com/poll/245606/update-gallup-presidential-approval-ratings.aspx
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** event (poll); nation
* **Update frequency:** Manual.
* **Raw table:** `approval_polls_raw` → **normalized table:** `approval_polls`
* **Variables:** `poll_id`, `pollster`, `start_date`, `end_date`, `sample_size`, `population_type`, `approve`, `disapprove`, `publication_date`
* **Description:** Poll-level approval data supplied as CSV in the documented template (see docs/DATA_SOURCES.md).
* **Known limitations:** No durable free structured source with poll-level history was identified (FiveThirtyEight feeds were discontinued in 2025; RealClearPolling has no API and scraping is out of scope). Gallup publishes tables, not downloads.

### Generic congressional ballot polls (manual CSV adapter) — Generic ballot poll-level observations

* **Dataset id:** `polls-generic-ballot` (phase 5)
* **Status:** MANUAL — tested with fixtures
* **Authoritative URL:** https://www.realclearpolling.com/polls/state-of-the-union/generic-congressional-vote
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** event (poll); nation
* **Update frequency:** Manual.
* **Raw table:** `generic_ballot_raw` → **normalized table:** `generic_ballot_polls`
* **Variables:** `poll_id`, `pollster`, `start_date`, `end_date`, `sample_size`, `population_type`, `generic_dem`, `generic_rep`, `publication_date`
* **Description:** Poll-level generic ballot data supplied as CSV in the documented template.
* **Known limitations:** Same as polls-approval.

### Race-specific polls (manual CSV adapter) — State/district race poll-level observations

* **Dataset id:** `polls-races` (phase 5)
* **Status:** MANUAL — tested with fixtures
* **Authoritative URL:** https://www.realclearpolling.com/
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** event (poll); state / district
* **Update frequency:** Manual.
* **Raw table:** `polls_raw` → **normalized table:** `polls`
* **Variables:** `poll_id`, `state`, `office`, `year`, `pollster`, `start_date`, `end_date`, `sample_size`, `population_type`, `dem_pct`, `rep_pct`, `publication_date`
* **Description:** Poll-level race polling supplied as CSV in the documented template.
* **Known limitations:** Same as polls-approval.

### Special-election results — Special elections with partisan baselines

* **Dataset id:** `special-elections` (phase 5)
* **Status:** TODO
* **Authoritative URL:** https://electionlab.mit.edu/data
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** event; state / district
* **Update frequency:** Event-driven.
* **Raw table:** `special_elections_raw` → **normalized table:** `special_elections`
* **Variables:** -
* **Description:** Special-election margins versus a baseline to measure national swing.
* **Known limitations:** Not implemented: MEDSL flags specials for Senate/House (special=True rows are already in election_results) but baselines need district-level presidential results, which MEDSL does not publish.

### American National Election Studies — Time Series Cumulative Data File — Respondent-level vote choice, party ID, ideology, demographics

* **Dataset id:** `anes-timeseries` (phase 6)
* **Status:** TODO
* **Authoritative URL:** https://electionstudies.org/data-center/
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** biennial/quadrennial; respondent
* **Update frequency:** After each election study.
* **Raw table:** `anes_raw` → **normalized table:** `individual_behavior_anes`
* **Variables:** -
* **Description:** Cumulative CSV (anes_timeseries_cdf_csv_*.csv) downloaded manually after login.
* **Known limitations:** Requires a registered ANES account; variable recodes (VCF0301 party ID, VCF0803 ideology, VCF0705 presidential vote, ...) not yet written.

### U.S. Census Bureau — CPS Voting and Registration Supplement microdata — Respondent-level registration and turnout

* **Dataset id:** `census-cps-voting` (phase 6)
* **Status:** TODO
* **Authoritative URL:** https://www.census.gov/data/developers/data-sets/census-microdata-api/cps/voting.html
* **Access method:** api
* **Credentials:** CENSUS_API_KEY
* **Frequency / geography:** biennial; respondent (state identified)
* **Update frequency:** Biennial (April after the election).
* **Raw table:** `cps_voting_raw` → **normalized table:** `individual_turnout_cps`
* **Variables:** -
* **Description:** Microdata API (api.census.gov/data/{year}/cps/voting/nov) variables PES1 (voted), PES2 (registered), PRTAGE, PESEX, PTDTRACE, PEHSPNON, PEEDUCA, HEFAMINC, GESTFIPS, PWSSWGT.
* **Known limitations:** Not implemented; requires CENSUS_API_KEY and paging over ~100k respondents per year.

### National Center for Education Statistics — NAEP Data Service — State average scale scores, grades 4 and 8, mathematics and reading

* **Dataset id:** `naep-state` (phase 6)
* **Status:** DONE — tested with fixtures
* **Authoritative URL:** https://www.nationsreportcard.gov/api_documentation.aspx
* **Access method:** api
* **Credentials:** none
* **Frequency / geography:** biennial; state
* **Update frequency:** Every two years.
* **Raw table:** `naep_raw` → **normalized table:** `naep`
* **Variables:** `average_score`, `pct_at_or_above_basic`, `pct_at_or_above_proficient`, `pct_advanced`
* **Ingest options:** `years`: comma-separated assessment years (default: 2003-2024 NAEP years)
* **Description:** NAEP Data Service GetAdhocData endpoint (MN:MN average scores and achievement-level percentages).
* **Known limitations:** Publication dates come from the release calendar rule (see release_calendar.naep).

### Pew Research Center — Religious Landscape Study — State religious composition by survey vintage (manual CSV adapter)

* **Dataset id:** `pew-religion` (phase 6)
* **Status:** MANUAL — tested with fixtures
* **Authoritative URL:** https://www.pewresearch.org/religious-landscape-study/
* **Access method:** manual
* **Credentials:** none
* **Frequency / geography:** occasional (2007, 2014, 2023-24); state
* **Update frequency:** Roughly every 7-10 years.
* **Raw table:** `religion_raw` → **normalized table:** `religion`
* **Variables:** `pct_evangelical_protestant`, `pct_mainline_protestant`, `pct_catholic`, `pct_religiously_unaffiliated`, `pct_attend_weekly`
* **Description:** State-level shares transcribed from Pew published tables or computed from the microdata (free account required) into the documented CSV template.
* **Known limitations:** Pew microdata downloads require a registered account and accepting terms; no automated access.

<!-- END GENERATED:data_sources -->

## Access findings (verified 2026-09-20)

| Source | Finding |
|---|---|
| Census API (ACS, PEP API, CPS microdata) | Keyless requests now return a "Missing Key" page; `CENSUS_API_KEY` is required. PEP, Gazetteer and urban/rural are fetched from `www2.census.gov` bulk files instead, which need no key. |
| MIT MEDSL (Harvard Dataverse) | Senate and President files download through the Dataverse API. The House dataset (`doi:10.7910/DVN/IG0UN2`) is guestbook-gated for every version: the API answers *You may not download this file without the required Guestbook response*, so it is a manual browser download. |
| BLS | `download.bls.gov` bulk files require an identifying User-Agent with contact info (403 otherwise) — set `ELECTIONDATA_CONTACT_EMAIL`. The v1 API works keyless but is limited to 25 series/query, 10 years/query, 25 queries/day. |
| QCEW open data | `data.bls.gov/cew/data/api/{year}/a/area/{fips}000.csv` works without a key; NAICS sector slices with hyphens (`31-33`) are not available as per-industry files, hence per-area files. |
| BEA | API requires a free `BEA_API_KEY`. |
| FEC | Bulk `cn{yy}.zip` / `weball{yy}.zip` redirect to S3 and need no key; header files live at `bulk-downloads/data_dictionaries/`. The OpenFEC API accepts `DEMO_KEY` with low rate limits. |
| EAC EAVS | Public-release CSV zips for 2020 (V1.2, posted 2023-12), 2022 (V1, 2023-06) and 2024 (V1 2025-06, V2 2026-02) have stable URLs; older years use different variable names. |
| NAEP | The NAEP Data Service (`GetAdhocData.aspx`) returns state means and achievement levels without a key. |
| Polling aggregators | RealClearPolling has no structured export; FiveThirtyEight's poll CSVs were discontinued in 2025; Gallup publishes tables, not downloads. No durable, licensed, structured poll-level source was identified, so polls are a manual CSV adapter. |
| Pew RLS, ANES | Microdata requires a registered account; manual. |

## Manual CSV templates

Place files under `data/raw/{source}/{dataset}/manual/` and run `electiondata ingest <id>`.
Percentages may be 0–100 or 0–1; `publication_date` (release date) is required for every row.
Templates (with illustrative rows) are in `tests/fixtures/`.

* `polls-races` → `data/raw/polling/polls-races/manual/race_polls.csv`
  `poll_id,state,district,office,year,pollster,pollster_grade,sponsor,start_date,end_date,publication_date,sample_size,population_type,mode,dem_candidate,rep_candidate,dem_pct,rep_pct,other_pct,undecided_pct,source_url`
* `polls-approval` → `data/raw/polling/polls-approval/manual/approval_polls.csv`
  `poll_id,pollster,president,start_date,end_date,publication_date,sample_size,population_type,approve,disapprove,source_url`
* `polls-generic-ballot` → `data/raw/polling/polls-generic-ballot/manual/generic_ballot_polls.csv`
  `poll_id,pollster,start_date,end_date,publication_date,sample_size,population_type,generic_dem,generic_rep,generic_other,undecided,source_url`
* `pew-religion` → `data/raw/pew/pew-religion/manual/religion.csv`
  `state,survey_year,publication_date,pct_evangelical_protestant,pct_mainline_protestant,pct_catholic,pct_religiously_unaffiliated,pct_attend_weekly,...,source_url`
* `medsl-house` → `data/raw/medsl/medsl-house/manual/1976-2024-house.tab` (the Dataverse file as downloaded).

## Expected raw formats for unimplemented sources

* **FEC election results** (`fec-election-results`): `federalelections{year}.xlsx` workbooks with
  sheets such as `2022 US Senate Results by State`, `2022 US House Results by State`, header
  rows that shift by year, `GENERAL VOTES`, `GENERAL %`, `GE WINNER INDICATOR` columns and
  footnote rows. Verified reachable at
  `https://www.fec.gov/resources/cms-content/documents/federalelections{year}.xlsx` (2020, 2022).
* **Census state-to-state migration flows**: `State_to_State_Migration_Table_{year}.xlsx`, a
  matrix with multi-row merged headers (current residence × previous residence) and
  interleaved MOE columns.
* **FEC committee reports** (`fec-committee-reports`): OpenFEC `/reports/{committee_type}/`
  JSON with `coverage_start_date`, `coverage_end_date`, `receipt_date`, `total_receipts_period`,
  `cash_on_hand_end_period` — the true point-in-time finance source.
* **CPS Voting Supplement** (`census-cps-voting`): `api.census.gov/data/{year}/cps/voting/nov`
  with `PES1` (voted), `PES2` (registered), `PRTAGE`, `PESEX`, `PTDTRACE`, `PEHSPNON`, `PEEDUCA`,
  `HEFAMINC`, `GESTFIPS`, `PWSSWGT`; paged, key required.
* **ANES** (`anes-timeseries`): `anes_timeseries_cdf_csv_*.csv` cumulative file; recodes
  needed for `VCF0301` (party id), `VCF0803` (ideology), `VCF0705` (presidential vote),
  `VCF0707`/`VCF0708` (House/Senate vote), `VCF0101` (age), `VCF0110` (education), `VCF0114`
  (income), `VCF0105a` (race), `VCF0104` (sex), `VCF0128` (religion), `VCF0901a` (state).
