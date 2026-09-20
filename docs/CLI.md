# CLI

Installed as `electiondata` (`uv run electiondata ...` or `.venv/Scripts/electiondata`).
Global flag: `-v/--verbose` for debug logging. Domain errors exit with code 2; failed
ingestions with code 1.

| Command | Purpose |
|---|---|
| `electiondata sources [--phase P] [--status S]` | Registry listing with status counts. Phase: number or name (`core`, `demographics`, `economics`, `political`, `environment`, `supplementary`). |
| `electiondata info <dataset-id>` | Registry metadata, ingest options, known limitations, last 5 runs. |
| `electiondata status [--markdown] [--write-docs]` | Registry joined with the manifest (last success, rows, last error). `--write-docs` rewrites the generated block of `docs/STATUS.md`. |
| `electiondata ingest <id>... [--phase P] [--source S] [-o k=v]... [--from-raw latest] [--allow-validation-errors] [--stop-on-error]` | Run ingestion. |
| `electiondata update [--include-manual]` | Ingest every dataset that can run automatically (skips missing-key datasets with a warning). |
| `electiondata transform` | Rebuild derived tables (`election_race_summary`). |
| `electiondata validate [table] [--fail-on-warning]` | Data-quality rules over processed tables; exit 1 on errors. |
| `electiondata rebuild-db` | Recreate DuckDB views over processed parquet. |
| `electiondata query "<sql>" [--limit N]` | Ad-hoc SQL against the views. |
| `electiondata build-features --year Y --office O [--as-of D] [--state ST]... [--no-write]` | Build the point-in-time feature dataset. |
| `electiondata audit-features Y O [D]` | Publication cut-offs per family and leakage flags for a build. |
| `electiondata runs [--dataset ID] [--limit N] [--failed]` | Ingestion manifest. |
| `electiondata audit [table]` | Rows, duplicate keys, missingness per processed table (JSON). |
| `electiondata docs` | Regenerate the generated blocks of STATUS.md, DATA_MODEL.md, DATA_SOURCES.md. |

## Examples

```bash
electiondata sources
electiondata sources --phase economics --status done
electiondata info census-pep-population

electiondata ingest medsl-senate medsl-president
electiondata ingest eac-eavs -o years=2022,2024
electiondata ingest --phase core
electiondata ingest --source BLS
electiondata ingest bls-qcew -o years=2022,2023
electiondata ingest fec-candidate-finance -o cycles=2026        # new snapshot for the current cycle
electiondata ingest medsl-senate --from-raw latest              # re-parse without downloading
electiondata update

electiondata transform
electiondata validate
electiondata validate turnout --fail-on-warning
electiondata rebuild-db
electiondata query "SELECT state, year, dem_two_party_share FROM election_race_summary WHERE office='senate' AND year=2024 ORDER BY 3"

electiondata build-features --year 2024 --office senate --as-of 2024-10-15
electiondata build-features --year 2026 --office senate --as-of 2026-10-15 --state PA --state GA
electiondata audit-features 2024 senate 2024-10-15

electiondata runs --failed
electiondata runs --dataset bls-laus --limit 5
electiondata status
electiondata status --write-docs
electiondata docs
```

## Exit codes

* `0` success
* `1` at least one ingestion failed, or validation errors were found
* `2` an `ElectionDataError` was raised (unknown dataset, storage error, ...)
