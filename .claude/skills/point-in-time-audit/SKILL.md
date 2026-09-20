---
name: point-in-time-audit
description: Audit an electiondata feature dataset for information leakage given an election year, office and as-of date — trace feature provenance, verify publication dates and vintages, identify values unavailable at the time, flag post-election information and check polling, finance and economic release cut-offs. Treat any leak as a model-validity failure.
---

# Point-in-time audit

Leakage invalidates a forecast. Be adversarial: assume every feature is guilty until its
publication date proves otherwise.

## Inputs

Election `year`, `office`, `as_of` (default: day before election day). Read
`docs/POINT_IN_TIME.md` first.

## Procedure

1. **Build or load the dataset.**
   `uv run electiondata audit-features <year> <office> <as_of>` prints, per family,
   `available`, `max_publication_date`, `estimated_share`, and `post_as_of_families` (must be
   empty). For an existing build, read the JSON sidecar next to
   `data/features/{office}_{year}_asof_{as_of}.parquet`.
2. **Trace provenance per family** (`metadata["families"][name]`): dataset ids, ingestion run
   ids → `data/manifests/runs/<run_id>.json` → raw URL/checksum. Confirm the rows were taken
   from `data/processed` tables whose `publication_date <= as_of`.
3. **Verify publication-date rules** for each used source against
   `src/electiondata/quality/release_calendar.py` and the source's real release calendar:
   * LAUS: latest `labor_month` must be at least ~3 weeks before `as_of`;
   * CPI/CES: `national_data_month` at most one month before `as_of`;
   * PEP: `population_vintage` must be ≤ `as_of` year − 1 (December release);
   * ACS: `acs_year` ≤ `as_of` year − 1 (September release) — if a September as_of, check the day;
   * QCEW `industry_year` ≤ `as_of` year − 1 (June release);
   * NAEP `naep_year` and urban/rural census year consistent with their release rules;
   * EAVS: `prev_turnout_year` must be an earlier election whose EAVS file was posted before
     `as_of` (the 2020 file we hold is V1.2 from Dec 2023 — a 2022 forecast legitimately lacks it).
4. **Vintages/revisions.** Flag families whose rows come from a vintage newer than `as_of`
   (`revision_vintage` in the processed table). BLS/BEA API series are current-vintage only:
   state this explicitly as a limitation of the backtest.
5. **Post-election information.** Confirm the following are absent or only from previous
   elections: certified turnout of the same election, same-year results, same-day presidential
   lean (`lean_year` must be < `year`), final campaign totals (`finance` family must be
   unavailable unless a snapshot was retrieved on/before `as_of` — check
   `metadata["families"]["finance"]` and the `retrieval_date` of `candidate_finance` rows).
6. **Polling cut-off.** If polls are present: every poll's `publication_date <= as_of`;
   windows (`polling_average_7d/30d`) use `end_date <= as_of`; no post-election polls.
7. **Finance cut-off.** `finance_coverage_end <= as_of`; snapshot `retrieval_date <= as_of`.
8. **Economic release cut-off.** Re-derive one state's `unemployment_rate` from
   `ed.economics.labor(state, as_of=...)` and confirm it matches the feature row.
9. **Targets.** `TARGET_COLUMNS` are labels; confirm no other column is a transformation of
   them (grep the transform code if a new feature was added recently).

## Output

```
Build: {office} {year} as_of={as_of}  rows=N  columns=M
Families used (max publication date / estimated share): ...
Families unavailable and why: ...
Vintage caveats: ...
LEAKS FOUND: none | list (family, column, publication_date, why)
Verdict: PASS | FAIL (a single leak = FAIL)
```

If FAIL: open a fix via `pipeline-maintenance` (rule or transform), rebuild, re-audit, and
record the incident in `docs/ROADMAP.md`/`docs/STATUS.md`.
