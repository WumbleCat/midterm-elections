# Roadmap

Ordered by value to the modelling dataset. Every entry names its current state, missing work,
blocker and the next concrete action.

## Critical

1. **Census ACS demographics (`census-acs-profile`)** — state: connector + normalizer written
   and fixture-tested (`normalize_acs`), never run live. Missing: a live pull to confirm
   variable ids (B01001/B15003/B19013/B19083/B17001/B03002/B05002/B05003) and value ranges.
   Blocker: `CENSUS_API_KEY` not configured. Next: request a key at
   `https://api.census.gov/data/key_signup.html`, set it in `.env`, run
   `electiondata ingest census-acs-profile -o years=2023`, compare PA `median_household_income`
   and `pct_bachelors_or_higher` with data.census.gov, then backfill 2010–2023 and flip the
   status to DONE.
2. **Point-in-time campaign finance (`fec-committee-reports`)** — state: TODO. The bulk
   `weball` file is a post-hoc snapshot, so historical backtests have no finance features.
   Missing: connector for OpenFEC `/reports/{committee_type}/` (or `/candidate/{id}/totals/`
   with `cycle`), keyed by `committee_id` + `coverage_end_date`, with `receipt_date` as
   `publication_date`, then a transform that builds race-level totals as of a date. Blocker:
   rate limits with `DEMO_KEY` (register an api.data.gov key). Next: implement for Senate
   principal committees 2018–2024 (join `candidates.principal_committee_id`), add a fixture from
   one real response, wire into `finance_features` as the preferred source.
3. **BEA state economy (`bea-state-gdp`, `bea-personal-income`, `bea-rpp`)** — state:
   connectors fixture-tested, blocked on `BEA_API_KEY`. Next: get a key
   (`https://apps.bea.gov/API/signup/`), run the three datasets, verify PA real GDP against
   BEA's iTable, flip to DONE. `real_gdp_growth`, `personal_income_growth`,
   `regional_price_parity` features then populate automatically.
4. **MEDSL House (`medsl-house`)** — state: MANUAL; parser fixture-tested on the documented
   layout, not on the real file. Next: download `1976-2024-house.tab` from
   `https://doi.org/10.7910/DVN/IG0UN2` (guestbook), place it in
   `data/raw/medsl/medsl-house/manual/`, run `electiondata ingest medsl-house`, fix any layout
   drift, add a real-row fixture, and extend feature builds to `office="house"` (the race key
   already supports `district`).

## High

5. **Poll-level sources (`polls-*`)** — state: manual CSV adapters + date-windowed averages
   are implemented and tested; no data ingested. Blocker: no durable, licensed, structured
   poll-level source identified (RealClearPolling has no API; 538 feeds discontinued). Next:
   decide on a source (options: a licensed feed, hand-curated CSVs, or an academic archive
   such as the Roper Center for historical presidential approval); at minimum load Gallup's
   historical approval table by hand into `approval_polls.csv` with release dates.
6. **EAVS earlier years and vintages** — state: 2020/2022/2024 only, one version per year
   (2020 is V1.2 posted Dec 2023, so a forecast made in Oct 2022 sees no 2020 turnout). Next:
   add 2016/2018 public-release files (variable names differ: map their item codes), ingest
   first-release versions where the EAC still hosts them (V1 2024) keyed by
   `revision_vintage`; add `voting_age_population` from PEP single-year age files
   (`sc-est{vintage}-agesex-civ.csv`) so `turnout_vap` can be computed.
7. **Urban/rural 2010 classification** — state: 2020 only, so 2012–2020 forecasts have no
   `pct_urban`. Next: parse `PctUrbanRural_State.xls` (2010; needs `xlrd`) in
   `UrbanRuralConnector` and key by census year.
8. **FEC official results (`fec-election-results`)** — state: TODO; URLs verified for 2020
   and 2022. Next: write an openpyxl parser for the Senate/House/President sheets with
   per-year header detection, use it as a cross-check against MEDSL (a reconciliation rule on
   `dem_votes`/`rep_votes` per race in `electiondata validate`).
9. **BLS vintage archive** — state: API/bulk return the current vintage only. Next: schedule
   monthly LAUS/CPI/CES pulls (GitHub Actions workflow exists) so `revision_vintage`
   accumulates; select across retrieval dates in `unemployment_features` with `latest_as_of`.

## Medium

10. **Special elections (`special-elections`)** — state: schema + swing aggregation exist;
    no source. Next: build the table from MEDSL rows with `special=True` (Senate) plus a
    hand-maintained CSV for House specials with a baseline margin (use the previous House
    result as baseline; district presidential results are not in MEDSL).
11. **Census migration flows (`census-migration-flows`)** — state: TODO. Net domestic
    migration is already covered by PEP components. Next: parse
    `State_to_State_Migration_Table_{year}.xlsx` (multi-row headers) into `migration_flows`.
12. **CPS Voting Supplement (`census-cps-voting`)** — needs `CENSUS_API_KEY`; implement paging
    over `api.census.gov/data/{year}/cps/voting/nov` and the recodes listed in
    DATA_SOURCES.md.
13. **ANES (`anes-timeseries`)** — manual download; write recodes for the cumulative file.
14. **Pew religion** — transcribe the 2014 and 2023-24 RLS state tables into the manual CSV
    (with publication dates), or compute from microdata after registering.
15. **Wages / real wages from QCEW + CPI** — `average_weekly_wage` is in the industry family;
    add `nominal_wage_growth` / `real_wage_growth` (needs two QCEW years published by as_of).

## Nice-to-have

16. Congressional-district features (ACS CD profiles, district partisan lean) for House
    modelling.
17. DuckDB materialized tables for large monthly series if parquet scans become slow.
18. `electiondata compare-runs` to diff row counts/values between two runs of a dataset.
19. Independent expenditures (`fec-independent-expenditures`, DEFERRED per specification).
20. Optional housing variables from ACS (B25077 median value, B25064 median rent, B25003
    tenure).
