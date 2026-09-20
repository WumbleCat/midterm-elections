# Implementation status

Hand-maintained summary (update after every pipeline session); the matrix below is generated
from the registry and the ingestion manifest with `electiondata status --write-docs`.

```
Last reviewed:        2026-09-20
Package test status:  109 unit tests pass (pytest tests/unit); 9 live integration tests pass,
                      2 skipped for missing CENSUS_API_KEY / BEA_API_KEY (pytest --run-integration)
Known broken sources: none among DONE datasets (see the "last error" column below)
Data store:           data/ on the author's machine; raw+processed are git-ignored, the manifest is versioned
```

Status meanings: **DONE** connector + real format + normalization + tests + verified live pull;
**PARTIAL** subset/caveat; **BLOCKED** implemented and fixture-tested but needs a credential to
run; **MANUAL** adapter for hand-downloaded files (documented template); **TODO** not
implemented; **DEFERRED** intentionally postponed.

<!-- BEGIN GENERATED:status -->
_Generated 2026-09-20 18:40 from the source registry and `data/manifests/ingestion_runs.parquet`. Do not edit inside the markers; run `electiondata status --write-docs`._

```
DONE: 13
PARTIAL: 0
TODO: 6
BLOCKED: 4
MANUAL: 5
DEFERRED: 1
```

| Phase | Source | Dataset id | Table | Status | Tested | Last successful pull | Rows | Last run | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EAC | `eac-eavs` | `turnout` | DONE | yes | 2026-09-20 | 167 | 2026-09-20 (success) | Only 2020, 2022 and 2024 public-release CSVs have stable URLs and a consistent item numbering; earlier years use different variable names. Negative EAVS codes (-88/-99 etc.) are treated as missing. Jurisdiction non-response is reported in n_jurisdictions_missing_ballots. |
| 1 | FEC | `fec-election-results` | `election_results` | TODO | no | - |  | - | Workbook layouts differ by year (sheet names, header rows, footnotes); parser not yet written. Files verified reachable at https://www.fec.gov/resources/cms-content/documents/federalelections{year}.xlsx for 2020/2022. |
| 1 | MEDSL | `medsl-house` | `election_results` | MANUAL | yes | - |  | - | Guestbook-gated download (API returns 'You may not download this file without the required Guestbook response'). Parser is fixture-tested on the documented 1976-2024 layout; vote 'mode' rows are collapsed (TOTAL preferred, otherwise summed) and runoff rows are excluded. |
| 1 | MEDSL | `medsl-president` | `election_results` | DONE | yes | 2026-09-20 | 4,737 | 2026-09-20 (success) | Some states report fusion/ballot-line splits; votes are summed per candidate and party assigned from the largest line. |
| 1 | MEDSL | `medsl-senate` | `election_results` | DONE | yes | 2026-09-20 | 3,743 | 2026-09-20 (success) | General-election stage only; Louisiana jungle primaries and runoffs follow MEDSL conventions. Dataset versions replace earlier ones (revision_vintage = Dataverse version). |
| 2 | Census | `census-acs-profile` | `demographics` | BLOCKED | yes | - |  | - | The Census API now rejects keyless requests ('Missing Key'); set CENSUS_API_KEY. Connector is fixture-tested but has not run live. 2020 1-year estimates were not released (experimental only). |
| 2 | Census | `census-gazetteer` | `geography` | DONE | yes | 2026-09-20 | 208 | 2026-09-20 (success) |  |
| 2 | Census | `census-migration-flows` | `migration_flows` | TODO | no | - |  | - | Excel layout has merged multi-row headers and MOE columns interleaved; parser not written. Net domestic migration is already available from census-pep-population. |
| 2 | Census | `census-pep-population` | `population` | DONE | yes | 2026-09-20 | 2,902 | 2026-09-20 (success) | Each vintage revises earlier years; all vintages are kept and distinguished by revision_vintage. The intercensal 2000-2010 file has no migration components in the same layout (population only). |
| 2 | Census | `census-urban-rural` | `urban_rural` | DONE | yes | 2026-09-20 | 56 | 2026-09-20 (success) | 2020 only; 2010 classification (PctUrbanRural_State.xls) not yet parsed. |
| 3 | BEA | `bea-personal-income` | `state_economy` | BLOCKED | yes | - |  | - | Requires BEA_API_KEY. Fixture-tested, not yet run live. |
| 3 | BEA | `bea-rpp` | `state_economy` | BLOCKED | yes | - |  | - | Requires BEA_API_KEY. Fixture-tested, not yet run live. |
| 3 | BEA | `bea-state-gdp` | `state_economy` | BLOCKED | yes | - |  | - | Requires BEA_API_KEY (free). Fixture-tested, not yet run live. Current vintage only; comprehensive revisions are not tracked. |
| 3 | BLS | `bls-ces-national` | `national_economy` | DONE | yes | 2026-09-20 | 1,350 | 2026-09-20 (success) | Current vintage only; payroll revisions are not tracked. publication_date estimated (month end + 8 days). |
| 3 | BLS | `bls-cpi` | `national_economy` | DONE | yes | 2026-09-20 | 1,472 | 2026-09-20 (success) | publication_date estimated (month end + 15 days). |
| 3 | BLS | `bls-laus` | `labor` | DONE | yes | 2026-09-20 | 30,957 | 2026-09-20 (success) | Bulk mode needs ELECTIONDATA_CONTACT_EMAIL because BLS requires an identifying User-Agent on download.bls.gov (403 otherwise). API mode without BLS_API_KEY is limited to 25 series/query, 10 years/query and 25 queries/day. Both return the current vintage only; publication_date is estimated from the release calendar (month end + 21 days) and annual benchmark revisions are not tracked. |
| 3 | BLS | `bls-qcew` | `industry` | DONE | yes | 2026-09-20 | 10,177 | 2026-09-20 (success) | Default pull covers a small year range (option years). Suppressed cells are null. |
| 4 | FEC | `fec-candidate-finance` | `candidate_finance` | DONE | yes | 2026-09-20 | 32,308 | 2026-09-20 (success) | Historical cycle files hold the FINAL totals (coverage end 12/31); pre-election snapshots for past cycles are only available via FEC API report filings (todo: fec-committee-reports). Point-in-time filters therefore exclude finance for past elections unless a snapshot retrieved before election day exists. |
| 4 | FEC | `fec-candidate-master` | `candidates` | DONE | yes | 2026-09-20 | 65,812 | 2026-09-20 (success) | Includes non-serious filers; join with results/finance to select major candidates. Historical cycle files are the final snapshot for that cycle. |
| 4 | FEC | `fec-committee-reports` | `candidate_finance` | TODO | no | - |  | - | Not implemented. DEMO_KEY rate limits are low; a registered api.data.gov key is recommended. |
| 4 | FEC | `fec-independent-expenditures` | `candidate_finance` | DEFERRED | no | - |  | - | Deferred: second-stage feature per the specification; bulk files are large and need candidate matching. |
| 5 | Polling | `polls-approval` | `approval_polls` | MANUAL | yes | - |  | - | No durable free structured source with poll-level history was identified (FiveThirtyEight feeds were discontinued in 2025; RealClearPolling has no API and scraping is out of scope). Gallup publishes tables, not downloads. |
| 5 | Polling | `polls-generic-ballot` | `generic_ballot_polls` | MANUAL | yes | - |  | - | Same as polls-approval. |
| 5 | Polling | `polls-races` | `polls` | MANUAL | yes | - |  | - | Same as polls-approval. |
| 5 | MEDSL/FEC/state offices | `special-elections` | `special_elections` | TODO | no | - |  | - | Not implemented: MEDSL flags specials for Senate/House (special=True rows are already in election_results) but baselines need district-level presidential results, which MEDSL does not publish. |
| 6 | ANES | `anes-timeseries` | `individual_behavior_anes` | TODO | no | - |  | - | Requires a registered ANES account; variable recodes (VCF0301 party ID, VCF0803 ideology, VCF0705 presidential vote, ...) not yet written. |
| 6 | Census | `census-cps-voting` | `individual_turnout_cps` | TODO | no | - |  | - | Not implemented; requires CENSUS_API_KEY and paging over ~100k respondents per year. |
| 6 | NAEP | `naep-state` | `naep` | DONE | yes | 2026-09-20 | 2,244 | 2026-09-20 (success) | Publication dates come from the release calendar rule (see release_calendar.naep). |
| 6 | Pew | `pew-religion` | `religion` | MANUAL | yes | - |  | - | Pew microdata downloads require a registered account and accepting terms; no automated access. |
<!-- END GENERATED:status -->

## Notes per phase

* **Phase 1 (core):** MEDSL Senate/President are complete 1976–2024 (3,743 / 4,737 candidate
  rows → 1,520 race summaries for President and Senate). EAVS turnout covers 2020/2022/2024
  (51 states + territories). MEDSL House needs the guestbook download (parser ready).
  FEC official spreadsheets are a TODO parser.
* **Phase 2 (demographics):** PEP population + components for vintages 2009, 2015–2019,
  2021–2024 (2,902 state-years), Gazetteer land area (2012/2016/2020/2024), 2020 urban/rural.
  ACS is implemented and fixture-tested but blocked on `CENSUS_API_KEY`.
* **Phase 3 (economics):** LAUS 1976–2026 via bulk file (30,957 state-months), CPI and
  CES/CPS national via API (1996–2026), QCEW 2023–2024 (10,177 rows). BEA connectors are
  blocked on `BEA_API_KEY`.
* **Phase 4 (political):** FEC candidate master and financial summaries for cycles 2010–2026
  (65,812 / 32,308 rows). Finance features are only point-in-time valid for snapshots
  retrieved before the forecast date (i.e. from the 2026 cycle onwards).
* **Phase 5 (environment):** manual CSV adapters for approval, generic ballot and race polls;
  special elections TODO.
* **Phase 6 (supplementary):** NAEP 2003–2024 state scores (2,244 rows). Pew manual adapter.
  CPS microdata and ANES TODO.
