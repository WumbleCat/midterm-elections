# electiondata — U.S. election data platform

A local-first, point-in-time-correct data platform for a state-by-state U.S. election model.
It ingests official sources (Census, BLS, BEA, FEC, MIT MEDSL, EAC, NAEP, …) into immutable
raw files, normalizes them into canonical Parquet tables with full provenance, exposes them
through DuckDB and a stable Python API, and builds modelling datasets that only use
information published on or before a chosen forecast date.

```
external sources → connectors → raw (immutable) → normalize/validate → processed Parquet
                → DuckDB views → point-in-time features → Python API / notebooks / models
```

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
git clone https://github.com/WumbleCat/midterm-elections.git
cd midterm-elections
uv sync --extra dev            # creates .venv and installs electiondata in editable mode
cp .env.example .env           # optional: API keys and contact email (see below)
uv run pytest tests/unit       # offline test suite
```

Windows note: if `uv` reports TLS certificate errors behind a corporate proxy, set
`UV_SYSTEM_CERTS=1`. The package itself verifies TLS against the OS trust store.

Credentials are optional. Without keys the following work out of the box: MEDSL results,
EAC EAVS, Census PEP/Gazetteer/urban-rural, BLS LAUS/CPI/CES/QCEW, FEC bulk files, NAEP.
Set `ELECTIONDATA_CONTACT_EMAIL` (BLS requires an identifying User-Agent for bulk files),
`CENSUS_API_KEY` for ACS and `BEA_API_KEY` for state GDP/income.

## Quick start

```bash
uv run electiondata sources                       # what is registered and its status
uv run electiondata ingest --phase core           # MEDSL results + EAVS turnout
uv run electiondata ingest bls-laus census-pep-population census-gazetteer census-urban-rural
uv run electiondata ingest fec-candidate-master fec-candidate-finance naep-state bls-cpi bls-ces-national
uv run electiondata transform && uv run electiondata validate && uv run electiondata rebuild-db
uv run electiondata build-features --year 2024 --office senate --as-of 2024-10-15
uv run electiondata status
```

## Python API

```python
import electiondata as ed

results = ed.elections.results(year=2024, office="senate", state="PA")   # race summary
turnout = ed.elections.turnout(year=2024, state="PA")
population = ed.demographics.population(state="PA", as_of="2024-06-01")
labor = ed.economics.labor(state="PA", as_of="2024-10-01")                # monthly LAUS
finance = ed.candidates.finance(state="PA", year=2024, office="senate", as_of="2024-10-15")
polls = ed.polls.races(year=2024, state="PA", office="senate", as_of="2024-10-15")

dataset = ed.features.build(year=2024, office="senate", as_of="2024-10-15")
ed.query("SELECT state, dem_two_party_share FROM election_race_summary WHERE year=2024 AND office='senate'")
```

See [docs/PACKAGE_API.md](docs/PACKAGE_API.md) for the full surface.

## Point-in-time warning

Every row carries `observation_date`, `publication_date` (flagged when estimated from a
release calendar), `retrieval_date`, `revision_vintage` and an ingestion run id.
`ed.features.build(..., as_of=T)` and every `as_of=` argument only use rows published on or
before `T`, and the feature builder refuses to emit a family whose data postdates the cut.
Known limits (current-vintage BLS/BEA series, post-hoc FEC bulk snapshots) are documented in
[docs/POINT_IN_TIME.md](docs/POINT_IN_TIME.md). The target columns are labels — never use
them as predictors.

## Data sources and status

13 datasets are DONE with verified live pulls (MEDSL Senate/President, EAVS, PEP, Gazetteer,
urban/rural, LAUS, CPI, CES, QCEW, FEC candidates/finance, NAEP); ACS and BEA connectors are
implemented but BLOCKED on API keys; polls, Pew and MEDSL House use MANUAL file adapters; the
rest are TODO/DEFERRED with documented next steps. The authoritative matrix is
[docs/STATUS.md](docs/STATUS.md) (generated from the registry + manifest) and the plan is
[docs/ROADMAP.md](docs/ROADMAP.md).

## Repository layout

```
src/electiondata/      package (api/, ingestion/, transform/, quality/, storage/, geo/, cli.py)
data/                  local store (raw/, staging/, processed/, features/, manifests/, electiondata.duckdb)
docs/                  ARCHITECTURE, DATA_MODEL, DATA_SOURCES, INGESTION, POINT_IN_TIME, PACKAGE_API,
                       CLI, STATUS, ROADMAP, ADDING_A_SOURCE
tests/                 unit (offline, recorded fixtures) and integration (live, opt-in)
.claude/skills/        Claude Code skills for ingestion, onboarding, maintenance, audits, status, docs
.github/workflows/     optional scheduled data update
```

`data/raw`, `data/staging`, `data/processed`, `data/features` and the DuckDB file are
git-ignored (reproducible from the pipeline); `data/manifests/ingestion_runs.parquet` is
versioned for provenance.

## Election Explorer (frontend)

An interactive choropleth explorer of U.S. federal elections since 1980, implemented
from the Claude Design screen `Election Explorer.dc.html`. It is a buildless static app
(ES modules + d3) served by Python:

    uv run python frontend/serve.py        # http://127.0.0.1:8000/

It currently runs on synthetic fixture data; `frontend/data/provider.js` is the seam
where the `electiondata` API replaces the fixtures. See `frontend/README.md`.

## Documentation

* [ARCHITECTURE.md](docs/ARCHITECTURE.md) — design and data flow
* [DATA_MODEL.md](docs/DATA_MODEL.md) — every canonical table, keys, units
* [DATA_SOURCES.md](docs/DATA_SOURCES.md) — every source: access, status, limitations, manual templates
* [INGESTION.md](docs/INGESTION.md) — runs, raw storage, manifests, options, re-runs
* [POINT_IN_TIME.md](docs/POINT_IN_TIME.md) — dates, vintages, leakage, backtesting
* [PACKAGE_API.md](docs/PACKAGE_API.md) · [CLI.md](docs/CLI.md)
* [STATUS.md](docs/STATUS.md) · [ROADMAP.md](docs/ROADMAP.md) · [ADDING_A_SOURCE.md](docs/ADDING_A_SOURCE.md)

## Development

```bash
uv run pytest tests/unit                       # 109 offline tests
uv run pytest tests/integration --run-integration   # live endpoints (needs network; keys for ACS/BEA)
uv run ruff check src tests && uv run ruff format src tests
uv run electiondata docs                       # regenerate STATUS / DATA_MODEL / DATA_SOURCES blocks
```
