# Adding a new source

Read `docs/DATA_SOURCES.md`, `docs/POINT_IN_TIME.md` and the specification section for the
source first. Prefer, in order: official API → official bulk CSV/ZIP → official downloadable
table → trusted standardized dataset → scraping only if nothing structured exists (and never
around anti-bot protections).

1. **Register the dataset** in `src/electiondata/ingestion/registry.py`: add a `SourceSpec`
   with a unique `id` (`<source>-<dataset>`), phase, frequency, geography, access method,
   `status=Status.TODO` for now, authoritative URL, `normalized_table` (an existing schema or
   a new one), `requires_api_key` if any, documented `options` and `known_limitations`.
2. **Schema.** If a new canonical table is needed, add a `TableSchema` in
   `quality/schemas.py` with a natural key, units (`share 0-1`, `percent 0-100`, `persons`,
   `votes`, ...) and descriptions. Shares are stored 0–1; document any 0–100 exception in the
   schema `notes`. Never collapse different frequencies into one table.
3. **Connector.** Create `ingestion/sources/<source>.py` (or extend it) with a class deriving
   from `Connector` (or `ManualFileConnector` for hand-downloaded files):
   * `dataset_id` = the registry id;
   * `fetch(ctx)` downloads through `ctx.download(url, filename, params=...)` or stores API
     payloads with `ctx.write_bytes(...)`; put per-artifact hints in `artifact.extra`
     (year, vintage, cycle) and make `parse` able to recover them from file names for
     `--from-raw`;
   * `parse(artifacts, ctx)` returns canonical rows using `geo.add_state_columns` /
     `normalize_state` (never a private state mapping) and `parties.normalize_party` for party
     labels, preserving `party_raw`;
   * set `observation_date`, `period_start`, `period_end`, `publication_date` and
     `publication_date_estimated`; add a rule in `quality/release_calendar.py` if the source
     has no per-row release date, and `revision_vintage` when vintages exist;
   * raise `SchemaChangeError` when expected columns are missing, `ParserError` on unreadable
     files, `DatasetUnavailableError` for missing years; never return an empty frame to hide a
     failure.
4. **Preserve raw files.** Do not post-process files on disk; the runner stores them
   immutably. Zip/xlsx/json are fine.
5. **Transformations.** Add pure functions in `transform/<family>.py` and wire the family into
   `transform/features.py` (`_load` table → as-of filter → merge on the race key → record the
   family in `families`).
6. **Validation.** Extend `quality/checks.py` if the table needs a new rule (reconciliation,
   category sets). Rules report; they never drop rows.
7. **Tests.** Record a small excerpt of the real file in `tests/fixtures/` (real rows for a
   couple of states) or, if the source is key-gated, a format-only fixture clearly named
   `*_format_fixture.*`. Add parse tests in `tests/unit/test_connectors.py`, an offline runner
   double in `tests/unit/test_runner_api_cli.py` if the family feeds features, and a live test in
   `tests/integration/test_live_sources.py` (marked `integration`).
8. **Docs.** Set `tested=True` and the right `status` in the registry, then run
   `electiondata docs` (regenerates DATA_SOURCES/DATA_MODEL/STATUS blocks). Add hand-written
   notes (manual templates, quirks) outside the generated markers.
9. **Integration run.** `electiondata ingest <id>` for real; check `electiondata runs`,
   validation output, row counts, and open the parquet to eyeball values against a known
   figure (e.g. a state's population or unemployment rate you can verify on the source site).
10. **STATUS.md.** Only mark `DONE` when: connector exists, real format handled, normalization
    works, tests pass, output written and a live pull succeeded. Otherwise `PARTIAL`
    (subset/caveat), `BLOCKED` (needs a credential), `MANUAL` (adapter for hand-downloaded
    files) or `TODO`. Record blockers and next actions in `docs/ROADMAP.md`.

## Checklist

- [ ] registry entry with options and limitations
- [ ] schema (units, key) and DATA_MODEL regenerated
- [ ] connector with provenance dates and vintages
- [ ] validation passes on a real pull
- [ ] unit tests on recorded fixture + integration test
- [ ] feature family wired (if applicable) and covered by `test_feature_build_is_point_in_time`
- [ ] `electiondata docs` + STATUS/ROADMAP updated
- [ ] no credentials in code, fixtures or manifests
