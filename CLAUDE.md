# CLAUDE.md — electiondata

Point-in-time-correct U.S. election data platform (`src/electiondata`). Read
`docs/STATUS.md` and `docs/ROADMAP.md` before any pipeline work; detailed procedures live in
`.claude/skills/`.

## Commands

```
uv sync --extra dev                         install (Windows TLS issues: UV_SYSTEM_CERTS=1)
uv run pytest tests/unit                    offline tests (must stay green)
uv run pytest tests/integration --run-integration   live tests (network; ACS/BEA need keys)
uv run ruff check src tests && uv run ruff format src tests
uv run electiondata sources|status|ingest|validate|transform|rebuild-db|build-features|runs|docs
```

## Rules

* The source registry (`ingestion/registry.py`) is the only place implementation status
  lives; `docs/STATUS.md`, `DATA_SOURCES.md`, `DATA_MODEL.md` generated blocks come from it
  via `electiondata docs`. Consult it before adding or changing connectors.
* Prefer official API → bulk file → downloadable table → standardized dataset; never scrape
  around anti-bot protections; never embed credentials (use `.env`, see `.env.example`).
* Raw files under `data/raw/` are immutable. Never delete or overwrite them to fix a run; use
  `--from-raw` to re-parse.
* Never fabricate observations, fixtures with invented values presented as real, or
  placeholder rows to make a pipeline look complete. Missing data stays missing; families
  become "unavailable".
* Every connector sets `observation_date`, `period_start/end`, `publication_date` and
  `publication_date_estimated`; use `geo.normalize_state` and `parties.normalize_party`; raise
  domain exceptions (`SchemaChangeError`, `ParserError`, `DatasetUnavailableError`) rather than
  returning empty frames.
* Point-in-time correctness is non-negotiable: every query/feature honours `as_of`; targets are
  labels, never features; snapshot sources are only valid when retrieved before `as_of`.
* Change behaviour → update tests (fixtures are recorded excerpts of real files; format-only
  fixtures are clearly named). Do not weaken tests to hide a wrong implementation.
* Only mark a dataset DONE after a verified live pull + passing tests + written output; update
  `docs/STATUS.md` (`electiondata status --write-docs` + the hand summary) after any
  ingestion-source work and `docs/ROADMAP.md` when blockers or scope change.
* Avoid destructive filesystem/database operations (`rm -rf data`, dropping tables) unless the
  user explicitly asks; DuckDB is disposable (`rebuild-db`), Parquet and raw are not.
* Commit meaningful changes with clear messages and push (the user asked for this).
