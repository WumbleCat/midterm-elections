# Python package API

All functions return pandas DataFrames (or a dict for national snapshots) and accept
`as_of=` to restrict rows to those published on or before that date. Tables that have not
been ingested raise `DatasetUnavailableError` (never a silent empty frame); filters that
match nothing return an empty frame.

```python
import electiondata as ed
```

## Elections

```python
# one row per race with dem/rep/other totals, shares, two-party share, margin, winner
ed.elections.results(year=2024, office="senate", state="PA")
ed.elections.results(year=[2020, 2024], office="president", state=["PA", "GA", "WI"])
ed.elections.results(year=2024, office="senate", level="candidate")      # as ingested
ed.elections.results(year=2020, office="senate", include_special=True)   # GA special etc.
ed.elections.results(office="senate", as_of="2022-01-01")                # only elections known by then

# EAVS registration / ballots with turnout_registered, turnout_population, mail_vote_share
ed.elections.turnout(year=2024, state="PA")

# state minus national Democratic two-party share per presidential year (+ smoothed lean)
ed.elections.partisan_lean(state="PA")

# previous-election features per race (prev_dem_share, prev_margin, lean_year, rolling averages)
ed.elections.history("senate", state="PA")
```

## Demographics

```python
ed.demographics.state(state="PA", year=2023)                 # ACS profile (needs census-acs-profile)
ed.demographics.population(state="PA", year=[2020, 2024])    # newest vintage per year
ed.demographics.population(state="PA", vintage=2019)         # one vintage
ed.demographics.population(state="PA", as_of="2024-06-01")   # vintages published by then
ed.demographics.geography(state="PA")                         # land area
ed.demographics.urban_rural(state="PA")
ed.demographics.snapshot("2024-10-15", state="PA")            # latest of everything as of a date + density
```

## Economics

```python
ed.economics.labor(state="PA", as_of="2024-10-01")                     # monthly LAUS
ed.economics.labor(state=["PA", "OH"], start="2020-01-01", end="2024-12-01")
ed.economics.labor_snapshot("2024-10-15", state="PA")                  # level + 3m/12m changes
ed.economics.industry(state="PA", year=2023)                           # QCEW rows
ed.economics.industry(as_of="2024-10-15", shares=True)                 # employment shares per state
ed.economics.state_economy(state="PA", measure="real_gdp")             # BEA (needs key)
ed.economics.national(measure="cpi_all_items", as_of="2024-10-15")
ed.economics.national(wide=True)
ed.economics.national_snapshot("2024-10-15")   # dict: unemployment, cpi_yoy, payroll growth, wages
```

## Candidates and finance

```python
ed.candidates.candidates(year=2024, state="PA", office="senate")
ed.candidates.incumbency(2024, "senate")                       # dem_incumbent / rep_incumbent / open_seat
ed.candidates.finance(state="PA", year=2024, office="senate")  # per-candidate summaries
ed.candidates.finance(year=2026, office="senate", as_of="2026-10-15", race_level=True)
#   -> dem_receipts, rep_receipts, dem_fundraising_share, log receipts, cash on hand
#   (only snapshots retrieved on/before as_of are used; see POINT_IN_TIME.md)
```

## Polls (manual CSV sources)

```python
ed.polls.races(year=2024, state="PA", office="senate", as_of="2024-10-15")
ed.polls.races(year=2024, office="senate", as_of="2024-10-15", aggregate=True)
ed.polls.approval(as_of="2024-10-15", aggregate=True)      # 7/30/90-day averages
ed.polls.generic_ballot(as_of="2024-10-15", aggregate=True)
```

## Features

```python
df = ed.features.build(year=2024, office="senate", as_of="2024-10-15")
fb = ed.features.build(year=2024, office="senate", as_of="2024-10-15", return_build=True)
fb.frame, fb.path, fb.metadata["families"], fb.families_unavailable
fb.summary()
ed.features.audit(2024, "senate", "2024-10-15")   # per-family publication cut-offs, leakage flags
ed.features.load("data/features/senate_2024_asof_2024-10-15.parquet")
```

Feature columns (when the family is available): targets (`dem_two_party_share`, ...),
political history (`prev_dem_share`, `prev_margin`, `state_partisan_lean`,
`weighted_state_lean`, `average_dem_share_last_2/3`, `previous_swing`), turnout
(`prev_turnout_registered`, `prev_turnout_population`, `prev_mail_vote_share`), demographics
(ACS shares, `median_age`, income, `gini_coefficient`, `poverty_rate`), population
(`population`, `population_growth_1y/4y/10y`, migration, `population_density`,
`log_population_density`), `pct_urban`, labour (`unemployment_rate`,
`unemployment_change_3m/12m`, `employment_growth_12m`), industry shares (`pct_manufacturing`,
`pct_healthcare`, `pct_government`, ...), state economy (`real_gdp_growth`, ...), national
(`national_unemployment_rate`, `cpi_yoy`, `payroll_growth_12m`, `real_wage_growth_12m`),
incumbency (`dem_incumbent`, `rep_incumbent`, `open_seat`), finance, polls, specials, NAEP
(`naep_math_grade4`, ...), religion.

## Registry, manifest, SQL

```python
ed.sources()                       # registry as a DataFrame
ed.list_specs(phase="economics")   # SourceSpec objects
ed.runs(dataset="bls-laus")        # manifest
ed.ingest_dataset("bls-laus", options={"start_year": 2015})
ed.ingest_phase("core"); ed.update_all()
ed.read_table("labor")             # raw processed table
ed.query("SELECT state, avg(unemployment_rate) FROM labor WHERE date >= '2024-01-01' GROUP BY 1")
ed.rebuild_database()
ed.filter_as_of(df, "2024-10-15")
```

## Stability

The module/function names above are the public contract. Source formats, storage layout and
SQL are internal and may change without affecting callers.
