"""``electiondata`` command-line interface (Typer)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

from .config import get_settings
from .exceptions import ElectionDataError
from .ingestion.registry import Status, get_spec, list_specs, status_counts
from .logging import configure_logging
from .paths import get_paths

app = typer.Typer(
    name="electiondata",
    help="Point-in-time-correct U.S. election data platform: ingest, validate, query, build features.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _print_frame(df: pd.DataFrame, max_rows: int = 200) -> None:
    with pd.option_context(
        "display.width",
        200,
        "display.max_columns",
        40,
        "display.max_colwidth",
        60,
        "display.max_rows",
        max_rows,
    ):
        typer.echo(df.to_string(index=False) if not df.empty else "(no rows)")


def _parse_options(items: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items or []:
        key, _, value = item.partition("=")
        if not key or not value:
            raise typer.BadParameter(f"options must look like key=value, got {item!r}")
        out[key.strip()] = value.strip()
    return out


@app.callback()
def _main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    configure_logging("DEBUG" if verbose else get_settings().log_level)


# ------------------------------------------------------------- registry


@app.command()
def sources(
    phase: Annotated[
        str | None, typer.Option(help="Filter by phase number or name (core, demographics, ...).")
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(help="Filter by status (DONE, PARTIAL, TODO, BLOCKED, MANUAL, DEFERRED)."),
    ] = None,
) -> None:
    """List every registered source/dataset with its implementation status."""
    specs = list_specs(phase=phase, status=status)
    df = pd.DataFrame(
        [
            {
                "phase": int(s.phase),
                "id": s.id,
                "source": s.source,
                "status": s.status.value,
                "access": s.access_method.value,
                "key": s.requires_api_key or "",
                "table": s.normalized_table,
                "dataset": s.dataset_name[:60],
            }
            for s in specs
        ]
    )
    _print_frame(df)
    typer.echo("\n" + "  ".join(f"{k}={v}" for k, v in status_counts().items()))


@app.command()
def info(dataset_id: str) -> None:
    """Show registry metadata, ingest options and recent runs for one dataset."""
    s = get_spec(dataset_id)
    typer.echo(f"{s.id}: {s.source_name} — {s.dataset_name}")
    for k in (
        "phase",
        "status",
        "access_method",
        "frequency",
        "geography",
        "requires_api_key",
        "authoritative_url",
        "normalized_table",
        "raw_table",
        "connector",
        "update_frequency",
        "tested",
    ):
        v = getattr(s, k)
        typer.echo(f"  {k:<18} {getattr(v, 'value', v)}")
    typer.echo(f"  {'description':<18} {s.description}")
    typer.echo(f"  {'limitations':<18} {s.known_limitations or '-'}")
    typer.echo(f"  {'variables':<18} {', '.join(s.variables) or '-'}")
    if s.options:
        typer.echo("  options:")
        for k, v in s.options.items():
            typer.echo(f"    --option {k}=...   {v}")
    from .storage.manifests import ManifestStore

    runs_df = ManifestStore().runs(dataset=s.id, limit=5)
    if not runs_df.empty:
        typer.echo("\nrecent runs:")
        _print_frame(runs_df[["run_id", "status", "started_at", "row_count", "error"]])


@app.command()
def status(
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Print the STATUS.md table instead of the console view."),
    ] = False,
    write_docs: Annotated[
        bool, typer.Option("--write-docs", help="Rewrite the generated block of docs/STATUS.md.")
    ] = False,
) -> None:
    """Implementation status per dataset, joined with the ingestion manifest."""
    from .docs_gen import status_frame, status_markdown, write_generated_docs

    if write_docs:
        for p in write_generated_docs(which=("status",)):
            typer.echo(f"updated {p}")
        return
    if markdown:
        typer.echo(status_markdown())
        return
    df = status_frame()
    _print_frame(
        df[
            [
                "phase",
                "dataset_id",
                "status",
                "tested",
                "last_success",
                "rows",
                "last_run",
                "last_run_status",
                "last_error",
            ]
        ]
    )
    typer.echo("\n" + "  ".join(f"{k}={v}" for k, v in status_counts().items()))


# ------------------------------------------------------------ ingestion


@app.command()
def ingest(
    dataset_ids: Annotated[
        list[str] | None, typer.Argument(help="Dataset ids (see `electiondata sources`).")
    ] = None,
    phase: Annotated[
        str | None, typer.Option(help="Ingest every runnable dataset of a phase.")
    ] = None,
    source: Annotated[
        str | None, typer.Option(help="Ingest every runnable dataset of a source (e.g. BLS).")
    ] = None,
    option: Annotated[
        list[str] | None,
        typer.Option(
            "--option",
            "-o",
            help="Connector option key=value (repeatable), e.g. -o years=2022,2024.",
        ),
    ] = None,
    from_raw: Annotated[
        str | None,
        typer.Option(
            help="Re-parse an existing raw directory ('latest' or a retrieval date) instead of downloading."
        ),
    ] = None,
    allow_validation_errors: Annotated[
        bool, typer.Option(help="Write processed output even when validation errors occur.")
    ] = False,
    stop_on_error: Annotated[bool, typer.Option(help="Stop at the first failed dataset.")] = False,
) -> None:
    """Ingest one or more datasets: download raw → parse → validate → processed parquet → manifest."""
    from .ingestion.runner import ingest_many

    ids = list(dataset_ids or [])
    if phase:
        ids += [s.id for s in list_specs(phase=phase) if s.runnable and s.status != Status.MANUAL]
    if source:
        ids += [s.id for s in list_specs(source=source) if s.runnable and s.status != Status.MANUAL]
    if not ids:
        raise typer.BadParameter("give dataset ids, --phase or --source")
    results = ingest_many(
        list(dict.fromkeys(ids)),
        options=_parse_options(option),
        from_raw=from_raw,
        fail_on_validation_error=not allow_validation_errors,
        stop_on_error=stop_on_error,
    )
    _report(results)


@app.command()
def update(
    include_manual: Annotated[bool, typer.Option(help="Also parse manual-file datasets.")] = False,
    option: Annotated[list[str] | None, typer.Option("--option", "-o")] = None,
) -> None:
    """Update every dataset that can run automatically (skips datasets whose API key is missing)."""
    from .ingestion.runner import update_all

    results = update_all(include_manual=include_manual, options=_parse_options(option))
    _report(results)


def _report(results: list) -> None:  # noqa: ANN001
    rows = []
    for r in results:
        rows.append(
            {
                "dataset": r.dataset_id,
                "status": r.status,
                "rows": r.rows,
                "errors": len(r.validation.errors) if r.validation else "",
                "warnings": len(r.validation.warnings) if r.validation else "",
                "error": (r.error or "")[:100],
            }
        )
    _print_frame(pd.DataFrame(rows))
    failed = [r for r in results if r.status == "failed"]
    if failed:
        raise typer.Exit(code=1)


# ------------------------------------------------------- transformation


@app.command()
def transform() -> None:
    """Rebuild derived tables (election_race_summary) from normalized data."""
    from .quality.checks import validate_table
    from .storage.parquet import read_table, write_processed
    from .transform.elections import race_summary

    results = read_table("election_results")
    summary = race_summary(results)
    report = validate_table("election_race_summary", summary, dataset="derived", source="transform")
    path = write_processed(summary, "election_race_summary", "derived")
    typer.echo(f"election_race_summary: {len(summary)} races -> {path}")
    typer.echo(report.summary())
    for issue in report.issues:
        typer.echo(f"  [{issue.severity}] {issue.rule}: {issue.message}")


@app.command()
def validate(
    table: Annotated[
        str | None, typer.Argument(help="Table name (default: every processed table).")
    ] = None,
    fail_on_warning: bool = False,
) -> None:
    """Run data-quality rules on processed tables and report issues."""
    from .quality.checks import validate_table
    from .storage.parquet import list_processed_files, read_parquet

    paths = get_paths()
    tables = (
        [table]
        if table
        else sorted(p.name for p in paths.processed.iterdir() if p.is_dir())
        if paths.processed.exists()
        else []
    )
    n_err = n_warn = 0
    for t in tables:
        for f in list_processed_files(t, paths):
            df = read_parquet(f)
            report = validate_table(
                t,
                df,
                dataset=f.stem,
                source=str(df["source"].iloc[0]) if "source" in df and len(df) else "",
            )
            typer.echo(report.summary())
            for issue in report.issues:
                typer.echo(
                    f"  [{issue.severity}] {issue.rule} field={issue.field} count={issue.count}: {issue.message}"
                )
                if issue.record:
                    typer.echo(f"      records: {issue.record}")
            n_err += len(report.errors)
            n_warn += len(report.warnings)
    typer.echo(f"\nvalidation: {n_err} errors, {n_warn} warnings across {len(tables)} tables")
    if n_err or (fail_on_warning and n_warn):
        raise typer.Exit(code=1)


@app.command("rebuild-db")
def rebuild_db() -> None:
    """Recreate the DuckDB views over the processed Parquet tables."""
    from .storage.duckdb import rebuild_database

    views = rebuild_database()
    typer.echo(f"{get_paths().duckdb_path}: {len(views)} views: {', '.join(views)}")


@app.command()
def query(sql: str, limit: int = 50) -> None:
    """Run SQL against the DuckDB views (e.g. "SELECT * FROM election_results LIMIT 5")."""
    from .storage.duckdb import query as run_query

    _print_frame(run_query(sql).head(limit))


@app.command("build-features")
def build_features(
    year: Annotated[int, typer.Option(help="Election year.")],
    office: Annotated[str, typer.Option(help="president | senate | house")],
    as_of: Annotated[
        str | None, typer.Option(help="Forecast date (YYYY-MM-DD); default: day before election.")
    ] = None,
    state: Annotated[
        list[str] | None, typer.Option(help="Restrict to states (repeatable).")
    ] = None,
    no_write: bool = False,
) -> None:
    """Build the modelling dataset using only data published on or before --as-of."""
    from .transform.features import build_features as _build

    fb = _build(year, office, as_of, states=state, write=not no_write)
    typer.echo(fb.summary())
    miss = fb.metadata.get("missingness", {})
    if miss:
        worst = sorted(miss.items(), key=lambda kv: -kv[1])[:10]
        typer.echo("highest missingness: " + ", ".join(f"{k}={v:.0%}" for k, v in worst))


@app.command("audit-features")
def audit_features_cmd(
    year: Annotated[int, typer.Argument(help="Election year.")],
    office: Annotated[str, typer.Argument(help="president | senate | house")],
    as_of: Annotated[
        str | None, typer.Argument(help="Forecast date; default: day before election.")
    ] = None,
) -> None:
    """Point-in-time audit of a feature build: publication cut-offs per family and leakage flags."""
    from .transform.features import audit_features
    from .transform.features import build_features as _build

    fb = _build(year, office, as_of, write=False, strict=False)
    typer.echo(json.dumps(audit_features(fb), indent=2, default=str))


# -------------------------------------------------------------- manifest


@app.command()
def runs(dataset: str | None = None, limit: int = 30, failed: bool = False) -> None:
    """Show the ingestion manifest (most recent first)."""
    from .storage.manifests import ManifestStore

    df = ManifestStore().runs(dataset=dataset, limit=None)
    if failed:
        df = df[df["status"] == "failed"]
    _print_frame(
        df.head(limit)[
            [
                "run_id",
                "dataset",
                "status",
                "started_at",
                "retrieval_date",
                "row_count",
                "validation_errors",
                "validation_warnings",
                "error",
            ]
        ]
    )


@app.command()
def docs() -> None:
    """Regenerate the generated blocks of docs/STATUS.md, DATA_MODEL.md and DATA_SOURCES.md."""
    from .docs_gen import write_generated_docs

    for p in write_generated_docs():
        typer.echo(f"updated {p}")


@app.command()
def audit(table: Annotated[str | None, typer.Argument()] = None) -> None:
    """Quick quality audit (rows, duplicates, missingness) of processed tables."""
    from .quality.checks import audit_frame
    from .storage.parquet import read_table

    paths = get_paths()
    tables = [table] if table else sorted(p.name for p in paths.processed.iterdir() if p.is_dir())
    for t in tables:
        typer.echo(json.dumps(audit_frame(read_table(t), t), indent=2, default=str))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        app()
    except ElectionDataError as exc:
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()


__all__ = ["Path", "app", "main"]
