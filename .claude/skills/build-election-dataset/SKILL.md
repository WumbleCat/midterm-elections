---
name: build-election-dataset
description: Construct a modelling-ready electiondata feature dataset for an election year, office and forecast as-of date ("build the 2026 Senate dataset as of Oct 15", "make a training set for 2018-2024"). Verifies required sources, builds, validates, and reports path, feature/row counts, missingness, unavailable families and reproducibility info.
---

# Build an election dataset

## 1. Choose parameters

* `year`: election year; `office`: `senate` | `president` (| `house` once MEDSL House is
  ingested); `as_of`: forecast date (default day before the election). For a training set,
  build one file per election with a consistent as-of offset (e.g. `YYYY-10-15`) and concatenate
  them yourself — do not mix as-of offsets silently.

## 2. Verify inputs

```
uv run electiondata status
uv run electiondata validate
```

Required for a useful build: `election_results` (MEDSL senate + president), `population`,
`geography`, `labor`, `national_economy`, `candidates`. Nice to have: `turnout`, `industry`,
`urban_rural`, `naep`, `demographics` (ACS — needs key), `state_economy` (BEA — needs key),
`candidate_finance` (only valid for snapshots retrieved before `as_of`), polls (manual).
Ingest what is missing with the `data-ingestion` skill first.

## 3. Build

```
uv run electiondata build-features --year 2026 --office senate --as-of 2026-10-15
```

or in Python:

```python
import electiondata as ed
fb = ed.features.build(year=2026, office="senate", as_of="2026-10-15", return_build=True)
print(fb.summary()); fb.metadata["families"]; fb.metadata["missingness"]
```

The build raises if any family contains rows published after `as_of`.

## 4. Validate

* `uv run electiondata audit-features <year> <office> <as_of>` → `post_as_of_families` empty.
* Check `rows` equals the number of races (Senate: ~33–35 regular races in a cycle; President:
  51). If the race universe fell back to "all states" (log warning), results/candidates for that
  cycle are missing.
* Inspect missingness: expected nulls are documented (finance for past cycles, ACS/BEA
  without keys, polls without manual data, `prev_*` for states with no earlier same-seat
  election, turnout for years before 2020).
* Spot-check one state row against the API queries in `docs/PACKAGE_API.md`.

## 5. Report

```
Dataset: data/features/{office}_{year}_asof_{as_of}.parquet (+ .json sidecar)
Rows: N races   Features: M columns (targets: dem_two_party_share, winner_party, ...)
Available families: ...
Unavailable families (reason): ...
Missingness (top 10): ...
Reproducibility: built_at, dataset ids + ingestion run ids per family (from the sidecar),
                 package version, as_of, election_date
Caveats: current-vintage BLS/BEA series; estimated publication dates share per family
```

Do not hand the user a dataset without naming the unavailable families and the target
columns that must be excluded from predictors.
