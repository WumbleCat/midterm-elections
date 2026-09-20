# Point-in-time correctness

A forecast made on date **T** may only use information that was publicly available on or
before T. This is a core architectural rule of the platform, not a modelling convention.

## Dates carried by every row

| Column | Meaning |
|---|---|
| `observation_date` | The date the value *refers to* (July 1 for population estimates, the reference month for LAUS, election day for results). |
| `period_start` / `period_end` | The reference period when the value spans one (calendar year for ACS/QCEW/BEA, a month for BLS series, a report period for FEC). |
| `publication_date` | When the value became public. **This is the column point-in-time filters use.** |
| `publication_date_estimated` | `True` when the date comes from a release-lag rule instead of a recorded release. |
| `retrieval_date` | When we downloaded the file. Also the vintage date for snapshot sources. |
| `revision_vintage` | Which release/vintage the row belongs to (PEP vintage year, MEDSL dataset version, EAVS V1/V2, QCEW year, or the retrieval date for API series). |
| `ingestion_run_id` | Links to the manifest row, hence to the URL, checksum and parser version. |

## The filter

```python
from electiondata.quality.point_in_time import filter_as_of, latest_as_of

avail = filter_as_of(df, "2024-10-15")                       # rows with publication_date <= as_of
latest = latest_as_of(df, "2024-10-15", keys=["state"], order_col="year")  # newest observation per key,
                                                             # from the newest vintage that existed
```

`filter_as_of` drops rows with a null publication date (they cannot be proven available);
pass `keep_unknown=True` only when you have documented why that is safe. If a frame has no
publication column at all it raises `PointInTimeError` unless `strict=False`.

Every public API function accepts `as_of=` and `ed.features.build(year, office, as_of)`
applies the cut to every feature family, then verifies no family's maximum publication date
exceeds `as_of`.

## Publication dates by source

| Source | How `publication_date` is set | Estimated? |
|---|---|---|
| MEDSL results | election date (unofficial totals are public that night; used only as *targets* or as *previous* elections for later years) | yes |
| EAC EAVS | month folder of the download URL (`/files/2023-06/` → 2023-06-30) — the vintage we hold; earlier V1 releases may have existed | yes |
| Census PEP | Dec 31 of the vintage year; each vintage kept separately | yes |
| Census Gazetteer / urban-rural | Dec 31 of the vintage year (urban/rural: two years after the census) | yes |
| Census ACS | Sept 30 of year+1 (1-year), Dec 31 of year+1 (5-year) | yes |
| BLS LAUS | reference month end + 21 days (state release) | yes |
| BLS CPI | month end + 15 days; CES/CPS national: month end + 8 days | yes |
| BLS QCEW annual | June 30 of year+1 | yes |
| BEA annual | Sept 30 of year+1 (RPP: Dec 31 of year+1) | yes |
| NAEP | Dec 31 of the assessment year (2009/2017/2024 → June 30 of the next year) | yes |
| FEC candidate master | min(retrieval date, June 30 of the cycle year) — registrations are public as filed | yes |
| FEC financial summaries | coverage end + 20 days, capped at retrieval date | yes |
| Manual polls / Pew | the release date supplied in the CSV (**required**) | no |

All rules live in `electiondata/quality/release_calendar.py` and err on the side of *later*
availability. Because we hold the data at retrieval time, an estimated date can never exceed
the retrieval date (the runner clips it).

## Revisions and vintages

* **PEP** publishes a new vintage every December that revises earlier years. We keep every
  vintage; `latest_as_of` picks the newest vintage published by `as_of`, and growth rates are
  computed *within* that vintage.
* **BLS/BEA API series** return only the current vintage. Annual benchmark revisions are not
  reconstructable from the API; `revision_vintage` records the retrieval date so repeated
  ingestions build a vintage archive over time. Treat historical backtests with these series
  as "current-vintage" backtests and say so.
* **FEC bulk summaries** are snapshots of *all* candidates at retrieval time. Truncating a
  post-election snapshot to reports dated before the election would keep only candidates who
  stopped filing, so `finance_features` uses a snapshot only if it was retrieved on or before
  `as_of`. Historical cycles therefore have no finance features until `fec-committee-reports`
  (FEC API filings with `receipt_date`) is implemented — see ROADMAP.
* **MEDSL** dataset versions replace earlier ones; the file's `version` column is the vintage.

## Leakage examples

| Leak | Why it is wrong | How the platform prevents it |
|---|---|---|
| Using 2024 certified turnout to predict 2024 | published after the election | turnout features use the previous same-type election (`prev_turnout_*`), filtered by publication date |
| Using final FEC totals (coverage 12/31) in a pre-election backtest | filed after election day | snapshot rule above; family reported *unavailable* rather than silently wrong |
| Using September unemployment on Oct 15 | state September figures are released ~Oct 20 | LAUS rule (month end + 21 days) gives August as the latest month |
| Using vintage-2024 population for a 2022 forecast | released Dec 2024 | vintage filter picks vintage 2021 |
| Using the 2024 presidential result as the partisan lean for the 2024 Senate race | same-day | lean uses the most recent presidential election strictly *before* the election year |
| A poll released after the forecast date | `publication_date` > as_of | manual CSV requires a release date; window functions filter on it |

## Backtesting correctly

```python
import electiondata as ed

for year in (2018, 2020, 2022, 2024):
    fb = ed.features.build(year=year, office="senate", as_of=f"{year}-10-15", return_build=True)
    print(fb.summary())                    # lists families unavailable at that date
    print(fb.families_unavailable)
```

Then read the JSON sidecar next to the parquet file: it records per family the max
publication date, the share of estimated dates, dataset ids and ingestion runs. Use
`electiondata audit-features YEAR OFFICE AS_OF` (or the `point-in-time-audit` skill) to
re-check a build.

## What is *not* protected automatically

* The `targets` columns (`dem_two_party_share`, `winner_party`, ...) are labels and are never
  filtered. Do not put them on the right-hand side of a model.
* "Current vintage" series (BLS/BEA API) — see above.
* Manual CSVs are only as honest as their `publication_date` column.
