---
name: update-documentation
description: Synchronize electiondata documentation after pipeline changes — STATUS.md, ROADMAP.md, DATA_SOURCES.md, DATA_MODEL.md, PACKAGE_API.md, CLI.md, README.md — regenerating machine-verifiable blocks from the registry/schemas/manifest and never claiming capabilities the code and tests do not demonstrate.
---

# Update documentation

1. **Regenerate** the generated blocks (registry, schemas, manifest are the sources of
   truth): `uv run electiondata docs` (writes the marker blocks in `docs/STATUS.md`,
   `docs/DATA_MODEL.md`, `docs/DATA_SOURCES.md`). Never edit inside
   `<!-- BEGIN GENERATED -->` markers by hand; change the registry/schema instead.
2. **STATUS.md hand summary** (top of file): `Last reviewed` = today; `Package test status` =
   the actual `uv run pytest tests/unit -q` and integration results you ran; `Known broken
   sources` from `uv run electiondata runs --failed`; keep the per-phase notes consistent
   with row counts in the generated table.
3. **ROADMAP.md**: remove items that are done (only if STATUS shows DONE with a live pull),
   add new blockers with state / missing work / blocker / next concrete action, keep the
   Critical/High/Medium/Nice-to-have ordering.
4. **DATA_SOURCES.md hand sections**: access findings (with verification date), manual CSV
   templates, expected raw formats for unimplemented sources.
5. **DATA_MODEL.md**: conventions and relationships when tables/keys change (generated table
   list handles columns).
6. **PACKAGE_API.md / CLI.md**: every public function/command must appear with a runnable
   example; run the examples (or the CLI smoke test) before documenting them. Remove
   examples for anything not implemented.
7. **README.md**: purpose, install, quick start, API/CLI examples, point-in-time warning,
   source status summary counts (must match `electiondata sources` counts), doc links.
8. **POINT_IN_TIME.md / INGESTION.md / ARCHITECTURE.md**: update when release-date rules,
   storage layout, runner behaviour or snapshot semantics change.
9. **Consistency check** (grep): dataset ids and table names mentioned in docs exist in the
   registry/schemas; option names match `SourceSpec.options`; counts (tests, datasets, rows)
   match command output.
10. Commit with a message listing the documents touched, and push.

Rule: if a capability is not exercised by a test or a recorded live run, describe it as
planned/partial — not as working.
