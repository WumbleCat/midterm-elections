---
name: pipeline-status
description: Answer "what data do we have?", "what is unfinished?", "which sources are broken?", "when were datasets last updated?" for electiondata by inspecting the source registry, ingestion manifest, processed tables, tests and docs/STATUS.md — never by guessing.
---

# Pipeline status

Ground every statement in a command output or a file; quote the numbers.

1. **Registry + manifest view:** `uv run electiondata status` — per dataset: status
   (DONE/PARTIAL/TODO/BLOCKED/MANUAL/DEFERRED), tested, last successful pull, rows, last run
   status and error. Summary counts are printed at the bottom.
2. **Recent activity:** `uv run electiondata runs --limit 20` and `--failed`.
3. **What is physically present:** `uv run electiondata audit` (rows/missingness per table) or
   `ls data/processed/*`; feature builds under `data/features/`; DuckDB views via
   `uv run electiondata query "SELECT table_name FROM information_schema.tables"` after
   `rebuild-db`.
4. **Coverage details** when asked (years, states, months): small pandas queries through the
   API, e.g. `ed.read_table("labor").groupby("state").date.agg(["min","max"])`.
5. **Unfinished work:** `docs/ROADMAP.md` (ordered, with blockers and next actions) and the
   registry `known_limitations` (`uv run electiondata info <id>`).
6. **Tests:** `uv run pytest tests/unit -q` for the current green/red state; mention that
   live tests need `--run-integration`.
7. **Docs freshness:** compare the `Last reviewed` line and generated timestamp in
   `docs/STATUS.md` with the manifest; if stale, run `uv run electiondata status --write-docs`
   and say so.

Answer format:

```
Available now (DONE, last pull, rows): ...
Blocked (needs credential): ...
Manual (needs a file): ...
Not implemented / deferred: ...
Broken (failed last run): ... (error, first seen)
Last updated: per dataset dates from the manifest
Next actions: top items from docs/ROADMAP.md
```
