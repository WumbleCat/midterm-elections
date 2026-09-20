# Ingestion

## One run, step by step

`electiondata ingest bls-laus` (or `ed.ingest_dataset("bls-laus")`) does:

1. look the dataset up in the registry (`ingestion/registry.py`); refuse if it has no
   connector or its required API key is missing (recorded as a failed run, not an exception);
2. create a run id `YYYYMMDDTHHMMSS-<dataset>-<6 hex>` and the raw directory
   `data/raw/{source}/{dataset}/{retrieval_date}/`;
3. `connector.fetch(ctx)` — downloads via `HttpClient` (retries on 408/425/429/5xx and
   connection errors with exponential backoff, capped at 60 s; 401/403 → `AuthenticationError`,
   404 → `DatasetUnavailableError`). Every file is streamed to a `.part` file, checksummed and
   placed immutably;
4. `connector.staging_frame()` (optional) → `data/staging/{dataset}/{date}.parquet`;
5. `connector.parse()` → canonical rows; the runner adds provenance, clips estimated
   publication dates to the retrieval date, enforces the schema, drops exact natural-key
   duplicates;
6. validation (`quality/checks.py`); errors abort the write unless
   `--allow-validation-errors`;
7. `data/processed/{table}/{dataset}.parquet` written atomically (tmp + rename);
8. manifest row + JSON record.

Logs are `key=value` lines on stderr with `run_id`, `dataset`, `url`, `path`, `sha256`,
`rows`, `validation_errors`, so each run answers *what ran, when, from where, how many rows,
where did raw and processed data go, did validation pass, what failed*.

## Raw storage

* Immutable: a re-download with identical content is detected by sha256 and reused (the
  manifest marks the artifact `reused=true`); different content is written as a sibling
  (`name.HHMMSS.ext`) and the original is untouched. Never delete raw directories to "fix" a
  run.
* Snapshot sources (FEC bulk files, BLS/BEA API series) accumulate one directory per retrieval
  date; that archive is what makes historical vintages reconstructable later.
* Manual sources read from `data/raw/{source}/{dataset}/manual/`.
* `data/raw`, `data/staging`, `data/processed`, `data/features` and the DuckDB file are
  git-ignored; `data/manifests/ingestion_runs.parquet` is versioned so provenance survives a
  clone.

## Manifest

`data/manifests/ingestion_runs.parquet` columns: `run_id, source, dataset, started_at,
completed_at, status (running|success|failed|skipped), retrieval_date, source_url, raw_path,
checksum, row_count, schema_version, parser_version, normalized_table, processed_path,
validation_errors, validation_warnings, error`. `manifests/runs/{run_id}.json` adds the
artifact list (path, URL with credentials redacted, sha256, size, HTTP status, request params),
validation issues (first 200) and notes (row-count change versus the previous successful run,
BLS messages, etc.).

```
electiondata runs                 # newest first
electiondata runs --failed
electiondata runs --dataset bls-laus
electiondata info bls-laus        # registry entry + last 5 runs
```

## Options

Connectors accept `--option key=value` (repeatable). Documented per dataset in
`electiondata info <id>` and DATA_SOURCES.md, e.g.

```
electiondata ingest eac-eavs -o years=2022,2024
electiondata ingest bls-qcew -o years=2021,2022,2023
electiondata ingest bls-laus -o mode=api -o start_year=2015
electiondata ingest census-gazetteer -o vintages=2012,2016,2020,2024
electiondata ingest fec-candidate-master -o cycles=2022,2024
electiondata ingest census-acs-profile -o years=2019,2021,2022,2023 -o survey=acs1
```

## Idempotency and re-runs

* Re-running a dataset replaces its processed file; rows are keyed by the schema's natural key
  (see DATA_MODEL.md), so nothing duplicates.
* `--from-raw latest` (or a retrieval date) re-parses an existing raw directory without
  downloading — the way to apply a parser fix to archived data.
* Transforms (`electiondata transform`, feature builds) are recomputed from processed tables.

## Update strategy

```
electiondata update                 # every automatic dataset whose key is available
electiondata ingest --phase core    # one phase
electiondata ingest --source BLS    # one source family
electiondata transform && electiondata validate && electiondata rebuild-db
electiondata status --write-docs    # refresh docs/STATUS.md
```

Recommended cadence: BLS monthly (after the state release around the 20th), FEC weekly during
a cycle (each retrieval is a new snapshot), Census/BEA/QCEW/NAEP/EAVS when new vintages appear.
`.github/workflows/update-data.yml` runs the keyless datasets on a schedule and fails visibly.

## Rate limits and credentials

* BLS API without `BLS_API_KEY`: 25 series/query, 10 years/query, 25 queries/day. The LAUS
  connector therefore defaults to the official bulk flat file (needs
  `ELECTIONDATA_CONTACT_EMAIL` for the User-Agent BLS requires).
* Census API now requires `CENSUS_API_KEY`; BEA requires `BEA_API_KEY`; FEC bulk needs none
  (`FEC_API_KEY=DEMO_KEY` is used for the API).
* Keys come from the environment or `.env`; they are redacted in logs, manifests and stored
  URLs.

## Error classes

`NetworkError`, `HTTPError`, `AuthenticationError`, `DatasetUnavailableError`,
`SchemaChangeError`, `ParserError`, `NormalizationError`, `ValidationError`, `StorageError`,
`PointInTimeError` (all subclasses of `ElectionDataError`). The runner records the class name
in the manifest `error` column so failures can be triaged without reading logs.
