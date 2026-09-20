---
name: data-quality
description: Audit electiondata's normalized tables for missingness, duplicates, invalid state/FIPS, unexpected categories, impossible shares/percentages, negative counts, broken date ranges, suspicious row-count changes, target leakage and post-as-of rows; produce a concise audit result. Use for "audit the data", "check data quality", "is the turnout table sane".
---

# Data quality audit

Produce a short, factual report; never "fix" data by editing parquet files — fixes go through
connectors/transforms and re-ingestion.

## Steps

1. **Inventory.** `uv run electiondata status` (rows per dataset, last success) and
   `uv run electiondata audit` (rows, duplicate key rows, top missingness per table).
2. **Rules.** `uv run electiondata validate` — read every error and warning with its
   `records`. Rules cover: required columns, natural-key duplicates, state/FIPS validity and
   agreement, shares in [0,1] / percents in [0,100], non-negative counts, unparseable dates,
   `period_start > period_end`, publication before observation (warning), null publication
   dates (warning — those rows are invisible to point-in-time filters), canonical parties,
   dem+rep+other reconciliation and candidate votes vs total, ballots vs registered, share
   groups summing to ~1.
3. **Manual checks in Python** (`uv run python -c` or a notebook) for what rules cannot see:
   * unexpected categories: `office`, `election_type`, `party`, `measure`, `industry_code`,
     `own_code`, `survey`, `subject`;
   * coverage gaps: states per year (`df.groupby("year").state.nunique()`), months per state
     (`labor`), cycles (`candidates`), vintages (`population.revision_vintage`);
   * suspicious jumps: year-over-year changes in population, unemployment, receipts; compare
     a few known values with the source site;
   * row-count drift: `electiondata runs --dataset <id>` and the runner note
     "row count changed ±N %";
   * duplicates across datasets feeding one table (e.g. two MEDSL files with the same
     race — `election_results` key includes `district`/`special`);
   * **target leakage**: no feature column equals or derives from the same-year outcome; in
     feature files, only the `TARGET_COLUMNS` may reference the election being modelled;
   * **post-as-of rows**: for any feature build, `electiondata audit-features Y O D` must show
     `post_as_of_families: []`; for tables, `ed.filter_as_of(df, as_of)` drops rows with
     `publication_date > as_of`.
4. **Reconciliation.** Race summaries vs candidate rows (`electiondata transform` output vs
   `election_results`), EAVS state totals vs known turnout figures, LAUS unemployment vs
   published rates for one month, PEP population vs Census press figures.
5. **Report** in this shape:

```
Tables audited: ...
Errors: N (rule → count → example records)
Warnings: N
Coverage gaps: ...
Suspicious values: ...
Leakage / as-of check: pass|fail (details)
Recommended actions: (connector/rule/doc changes, never manual data edits)
```

6. If the audit finds a real defect, route it to `pipeline-maintenance` (parser/rule fix) and
   note it under "Known broken sources" in `docs/STATUS.md`.
