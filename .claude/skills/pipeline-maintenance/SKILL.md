---
name: pipeline-maintenance
description: Diagnose and repair electiondata ingestion failures ("why did bls-laus fail", "the EAVS parser broke", "fix the failed runs"). Inspects the manifest and run JSON, reproduces, classifies the failure (API, schema change, network, credentials, parser, validation, transformation, storage), fixes the root cause, reruns tests and ingestion, and updates docs — without ever deleting historical raw data.
---

# Pipeline maintenance

## 1. Find the failure

```
uv run electiondata runs --failed
uv run electiondata runs --dataset <id> --limit 5
```

Open `data/manifests/runs/<run_id>.json`: `error` (exception class + message), `artifacts`
(URLs, HTTP status, checksums), `validation_issues`, `notes` (row-count changes, BLS
messages, traceback for unexpected exceptions).

## 2. Classify

| Error class / symptom | Category | Typical fix |
|---|---|---|
| `NetworkError`, `ConnectError`, TLS `CERTIFICATE_VERIFY_FAILED` | network | retry later; corporate proxy → OS trust store is used by default, check `ELECTIONDATA_SSL_VERIFY`; BLS bulk 403 → set `ELECTIONDATA_CONTACT_EMAIL` |
| `AuthenticationError`, "not configured", "Missing Key" | credentials | set the env var named in the error in `.env`; never commit it |
| `HTTPError ... daily threshold` (BLS) | API quota | wait for the next day, use `-o mode=bulk` for LAUS, or set `BLS_API_KEY` |
| `DatasetUnavailableError` 404 / "not yet available" | upstream URL/year | probe with curl; update the URL table in the connector (e.g. `EAVS_FILES`, `PEP_FILES`) and record the verification date in a comment |
| `SchemaChangeError` missing columns / field count | upstream schema change | inspect the raw file under `data/raw/...`; update column maps; bump `parser_version`; add/refresh the fixture; re-parse with `--from-raw` |
| `ParserError` | parser | same as above; check encoding/zip contents |
| `NormalizationError` | schema enforcement | a required column is null/missing: fix the mapping, not the schema, unless the schema is wrong |
| `ValidationError` | data quality | read the rule + records; decide whether the data is wrong (fix parser), the rule is too strict (adjust rule with justification), or the upstream file is genuinely bad (document, keep failed) |
| `StorageError` | storage | disk/permissions/locked DuckDB file; never delete raw |

## 3. Reproduce and fix

* Re-parse without downloading: `uv run electiondata ingest <id> --from-raw latest`.
* Write the failing case as a unit test first when the cause is a parser/schema issue (add a
  small excerpt of the offending raw file to `tests/fixtures/`).
* Fix the root cause in the connector/transform; keep the old behaviour for old files if the
  upstream layout differs by year (branch on year/columns, do not fork connectors).
* `uv run pytest tests/unit && uv run ruff check src tests`.
* Rerun ingestion for real if it is safe (idempotent; raw is immutable). Confirm
  `electiondata runs` shows success and the row count is plausible versus the previous success.

## 4. Document

* If the upstream schema changed: note it in the registry `known_limitations` and in
  `docs/DATA_SOURCES.md` (hand section), bump `parser_version`.
* `uv run electiondata status --write-docs`; update the hand summary ("Known broken
  sources") and `docs/ROADMAP.md` if the fix is partial or blocked.
* Commit and push.

## Never

* delete or rewrite files under `data/raw/` to make a run pass;
* mark a run successful by hand in the manifest;
* weaken validation rules without stating why in the commit and the docs.
