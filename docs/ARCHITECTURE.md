# Architecture

`electiondata` is a local-first data platform for a state-by-state U.S. election model. It
turns heterogeneous official sources into a small set of canonical tables with explicit
provenance, and builds modelling datasets that only use information available at a chosen
forecast date.

```
 external sources          ingestion              store                       consumers
 ────────────────          ─────────              ─────                       ─────────
 Census (PEP, ACS, ...)  ┐
 BLS (LAUS, CPI, QCEW)   │  connectors      raw/{source}/{dataset}/{date}/    Python API
 BEA regional accounts   │  (fetch+parse)   ── immutable downloads, sha256    ed.elections
 MIT MEDSL results       ├─────────────►                                       ed.demographics
 EAC EAVS                │                  staging/{dataset}/{date}.parquet   ed.economics
 FEC bulk files          │  runner          ── as-received tables              ed.candidates
 NAEP data service       │  normalize ───►                                     ed.polls
 manual CSVs (polls,Pew) ┘  validate        processed/{table}/{dataset}.parquet ed.features
                            manifest        ── canonical schemas + provenance        │
                                │                       │                            ▼
                                ▼                       ▼                    features/{office}_{year}_asof_{date}.parquet
                        manifests/ingestion_runs.parquet   electiondata.duckdb (views over parquet)
```

## Layers

| Layer | Package | Responsibility |
|---|---|---|
| Configuration | `electiondata.config`, `paths` | Environment variables, `.env`, data directory layout. Secrets never logged. |
| Geography | `electiondata.geo` | The single canonical state table (name/abbr/FIPS) and `normalize_state`. Every connector uses it. |
| HTTP | `electiondata.http` | Retries with exponential backoff, checksum-verified streaming downloads, OS trust store TLS, credential redaction. |
| Registry | `ingestion.registry` | One `SourceSpec` per dataset: phase, access method, status, table, connector, options. Drives CLI, docs and orchestration. |
| Connectors | `ingestion.sources.*` | `fetch(ctx)` downloads raw artifacts; `parse(artifacts, ctx)` returns canonical rows. Nothing else knows source formats. |
| Runner | `ingestion.runner` | fetch → raw (immutable) → staging → parse → provenance → schema → dedupe → validate → processed parquet → manifest. |
| Quality | `quality.schemas`, `quality.checks`, `quality.point_in_time`, `quality.release_calendar` | Explicit table schemas, validation rules, as-of filters, publication-date rules. |
| Storage | `storage.parquet`, `storage.duckdb`, `storage.manifests` | Atomic parquet writes, DuckDB views, run manifest. |
| Transforms | `transform.*` | Pure DataFrame functions: race summaries, partisan lean, turnout rates, economic changes, industry shares, finance/incumbency, poll averages, feature assembly. |
| API | `electiondata.api.*` | Stable user-facing functions returning DataFrames. Hide SQL and paths. |
| CLI | `electiondata.cli` | `electiondata sources|status|ingest|update|transform|validate|rebuild-db|query|build-features|audit-features|runs|docs|audit`. |

## Data flow in detail

1. **Fetch.** A connector asks `IngestContext.download()` (or `write_bytes()` for API
   responses) to store artifacts under `data/raw/{source}/{dataset}/{retrieval_date}/`.
   Existing files are never overwritten: identical content is reused (same checksum),
   different content gets a time-stamped sibling.
2. **Staging.** Optionally the as-received table is written to
   `data/staging/{dataset}/{retrieval_date}.parquet` for debugging schema changes.
3. **Parse/normalize.** The connector maps the raw layout to the canonical table columns and
   sets `observation_date`, `period_start/end`, `publication_date` and
   `publication_date_estimated` (see [POINT_IN_TIME.md](POINT_IN_TIME.md)). The runner adds
   `source`, `dataset_id`, `retrieval_date`, `ingestion_run_id`, clips estimated publication
   dates to the retrieval date, enforces the schema and de-duplicates on the natural key.
4. **Validate.** Rules in `quality.checks` report issues with source/dataset/table/field/
   record/rule. Errors block the processed write (override with `--allow-validation-errors`).
5. **Write.** `data/processed/{table}/{dataset_id}.parquet` is replaced atomically. A table is
   the union of its dataset files (DuckDB reads the directory with `union_by_name`).
6. **Manifest.** `data/manifests/ingestion_runs.parquet` gets one row per run; the full
   record (artifacts, params, validation issues, notes) is in `manifests/runs/{run_id}.json`.
7. **DuckDB.** `electiondata rebuild-db` recreates one view per table plus `ingestion_runs`.
   The DuckDB file is disposable; parquet is the durable copy.
8. **Features.** `transform.features.build_features(year, office, as_of)` reads processed
   tables, applies the as-of cut to every family, joins on the modelling key, verifies that no
   family's maximum publication date exceeds `as_of`, and writes
   `data/features/{office}_{year}_asof_{date}.parquet` plus a JSON sidecar with provenance.

## Modelling key

`state × election year × office` (Senate/President). House rows carry `district` and the
transforms already key on `(state, district)` for `office="house"`; the House results table
is populated through the manual MEDSL download (see STATUS).

## How updates propagate

Re-running `electiondata ingest <dataset>` (or `update`) replaces only that dataset's
processed file. Derived tables (`electiondata transform`) and feature builds are recomputed
from processed tables on demand, so nothing downstream caches stale data. Snapshot-style
sources (FEC bulk files) accumulate one raw snapshot per retrieval date; point-in-time
features pick the newest snapshot retrieved on or before the forecast date.

## Design principles

* Explicit over clever: one class per connector, plain pandas transforms, no framework.
* Every row is traceable to a run, a URL, a checksum and a publication date.
* Missing data is represented as missing (or a family marked unavailable), never estimated
  from later information or fabricated.
* Everything works offline from recorded fixtures; live access is opt-in.
