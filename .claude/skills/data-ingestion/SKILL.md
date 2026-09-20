---
name: data-ingestion
description: Safely ingest or update one or more electiondata datasets (e.g. "ingest the latest Census data", "update BLS", "refresh phase 2", "pull the latest election results"). Runs the registry-driven pipeline, preserves raw files, checks the manifest, validation and row counts, and updates docs/STATUS.md truthfully.
---

# Data ingestion

Use for any request to pull, refresh or update source data. Never fabricate rows; if a source
cannot be fetched, record the failure and say so.

## Procedure

1. **Map the request to dataset ids.** `uv run electiondata sources` (filter with
   `--phase`/`--status`). "Census" → `census-pep-population`, `census-gazetteer`,
   `census-urban-rural`, `census-acs-profile` (needs `CENSUS_API_KEY`); "BLS" → `bls-laus`,
   `bls-cpi`, `bls-ces-national`, `bls-qcew`; "election results" → `medsl-senate`,
   `medsl-president` (+ `medsl-house` manual); "turnout" → `eac-eavs`; "FEC" →
   `fec-candidate-master`, `fec-candidate-finance`; phases via `--phase core|demographics|
   economics|political|environment|supplementary`.
2. **Check preconditions.** `uv run electiondata info <id>`: status, required key, options,
   known limitations. Confirm the access method is the official structured one (registry
   `access_method`); do not add scraping. If a key is missing, say which env var and stop for
   that dataset (the runner records a failed run). BLS bulk needs
   `ELECTIONDATA_CONTACT_EMAIL`; the keyless BLS API has a 25-queries/day cap.
3. **Inspect the connector** (`src/electiondata/ingestion/sources/<source>.py`) if the request
   involves new years/options; pass options with `-o key=value` (e.g. `-o years=2024`,
   `-o cycles=2026`, `-o start_year=2015`).
4. **Run.** `uv run electiondata ingest <ids...>` (or `--phase`, `--source`, `update`). Watch
   the log lines `raw artifact stored` (path, sha256, reused) and `ingest success/failed`.
5. **Verify.**
   * `uv run electiondata runs --limit 10` — status, row_count, validation errors/warnings;
   * compare `row_count` with the previous successful run (the runner logs a note when it moves
     by more than 25 %) and explain any large change (new years? upstream revision?);
   * `uv run electiondata validate <table>` — read every error/warning and its `records`;
   * spot-check values with the API (`ed.elections.results(...)`, `ed.economics.labor(...)`)
     against a figure you can verify on the source site;
   * confirm raw files exist under `data/raw/{source}/{dataset}/{date}/` and were not
     overwritten (identical content is `reused=True`, different content gets a suffixed file).
6. **Downstream.** `uv run electiondata transform && uv run electiondata rebuild-db` if
   election results changed; rebuild affected feature datasets if the user relies on them.
7. **Document.** `uv run electiondata status --write-docs`; edit the hand summary at the top of
   `docs/STATUS.md` (last reviewed date, test status, known broken sources). If a source failed,
   leave it failed in the manifest and add the blocker + next action to `docs/ROADMAP.md`.
8. **Commit and push** the docs/manifest changes with a message naming the datasets and row
   counts.

## Do not

* delete or edit anything under `data/raw/`;
* mark a dataset DONE without a successful live pull in the manifest;
* silence validation errors with `--allow-validation-errors` unless the user accepts the
  documented reason;
* hard-code API keys or contact emails in code or fixtures.
