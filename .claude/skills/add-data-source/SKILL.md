---
name: add-data-source
description: Add a new source or dataset connector to electiondata (register it, implement fetch/parse with provenance and point-in-time dates, preserve raw files, validate, test with recorded fixtures, document, run a live integration, update STATUS). Use for "add source X", "implement the FEC results parser", "support ACS 5-year".
---

# Add a data source

Follow `docs/ADDING_A_SOURCE.md` step by step; this skill adds the checks that keep the
platform honest.

## Before writing code

1. Read the relevant section of the specification (`docs/DATA_SOURCES.md` summarises it;
   the original spec is `us_election_data_ingestion_specification.txt` if present) and
   `docs/POINT_IN_TIME.md`.
2. Read `src/electiondata/ingestion/registry.py` — the dataset may already exist as TODO/
   BLOCKED/MANUAL with documented limitations and expected raw format.
3. Read the most similar connector (`ingestion/sources/`): `bls.py` for API series,
   `census.py` for bulk CSV/XLSX, `fec.py` for zipped pipe files, `medsl.py` for Dataverse,
   `polling.py`/`pew.py` for manual CSV adapters.
4. Probe the endpoint with `curl` (status code, content type, a few rows). Confirm the access
   method is official/structured. If the source needs a login, licence acceptance or an
   API key you do not have, plan a `ManualFileConnector` or a BLOCKED connector instead of a
   scraper.

## Implementation checklist

* Registry entry: id, phase, frequency, geography, access method, `requires_api_key`,
  `normalized_table`, `connector`, `options`, `known_limitations`, `update_frequency`,
  `tested=False` until tests exist.
* Schema: reuse or add a `TableSchema` in `quality/schemas.py` (natural key, units, nullable).
* Connector: `fetch` via `ctx.download`/`ctx.write_bytes` (immutable raw), `parse` returning
  canonical rows with `geo.add_state_columns`, `parties.normalize_party`, and the five
  point-in-time columns; add a release-lag rule to `quality/release_calendar.py` when the
  source has no release date and set `publication_date_estimated=True`; set
  `revision_vintage` for vintaged sources.
* Make `parse` work from file names alone so `--from-raw` re-parsing works.
* Errors: `SchemaChangeError` for missing columns, `ParserError` for unreadable files,
  `DatasetUnavailableError` for missing years; never return empty frames on failure.
* Transform + feature family if the table feeds the model (`transform/features.py`).
* Tests: recorded excerpt of the real file in `tests/fixtures/` (real rows; format-only
  fixtures only when the source is inaccessible, named `*_format_fixture.*`), parse test in
  `tests/unit/test_connectors.py`, offline runner double in `tests/unit/test_runner_api_cli.py`
  if it feeds features, live test in `tests/integration/test_live_sources.py`.
* Run `uv run pytest tests/unit`, `uv run ruff check src tests`, then the live ingestion
  `uv run electiondata ingest <id>`; inspect the parquet and the manifest row.
* Docs: `uv run electiondata docs`, hand notes in `docs/DATA_SOURCES.md` (access findings,
  manual template), `docs/STATUS.md` summary, `docs/ROADMAP.md` entry removed or updated,
  `docs/PACKAGE_API.md` if the API grew.
* Status: DONE only after the live pull succeeded; otherwise PARTIAL/BLOCKED/MANUAL with the
  reason in `known_limitations`.
* Commit and push.

## Provenance requirements (non-negotiable)

Every row must have `source`, `source_url`, `dataset_id`, `retrieval_date`, `ingestion_run_id`
(added by the runner) and connector-set `observation_date`, `period_start`, `period_end`,
`publication_date`, `publication_date_estimated`, `revision_vintage` (nullable). If you cannot
determine when a value became public, say so in `known_limitations` and use the most
conservative (latest) defensible rule.
