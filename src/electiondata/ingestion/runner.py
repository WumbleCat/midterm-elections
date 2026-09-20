"""Ingestion orchestration: registry → connector → raw → parse → normalize → validate → processed → manifest."""

from __future__ import annotations

import datetime as dt
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings, get_settings
from ..exceptions import (
    AuthenticationError,
    DatasetUnavailableError,
    ElectionDataError,
    ValidationError,
)
from ..http import HttpClient
from ..logging import get_logger
from ..paths import DataPaths, get_paths
from ..quality.checks import ValidationReport, compare_row_counts, validate_table
from ..quality.schemas import SCHEMAS, enforce_schema
from ..storage.manifests import ManifestStore, RunRecord, new_run_id
from ..storage.parquet import write_parquet_atomic, write_processed
from .base import IngestContext, RawArtifact
from .registry import Phase, SourceSpec, Status, get_spec, list_specs

log = get_logger("runner")

SCHEMA_VERSION = "1"


@dataclass
class IngestResult:
    dataset_id: str
    run_id: str
    status: str
    rows: int = 0
    raw_dir: Path | None = None
    processed_path: Path | None = None
    validation: ValidationReport | None = None
    error: str | None = None
    artifacts: list[RawArtifact] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "success"


def _dedupe(df: pd.DataFrame, key: tuple[str, ...]) -> tuple[pd.DataFrame, int]:
    cols = [k for k in key if k in df.columns]
    if not cols:
        return df, 0
    before = len(df)
    out = df.drop_duplicates(subset=cols, keep="last")
    return out, before - len(out)


def _add_provenance(
    df: pd.DataFrame, spec: SourceSpec, ctx: IngestContext, artifacts: list[RawArtifact]
) -> pd.DataFrame:
    out = df.copy()
    out["source"] = spec.source
    out["dataset_id"] = spec.id
    out["retrieval_date"] = pd.Timestamp(ctx.retrieval_date)
    out["ingestion_run_id"] = ctx.run_id
    if "source_url" not in out.columns:
        out["source_url"] = artifacts[0].url if artifacts else None
    if "publication_date_estimated" not in out.columns:
        out["publication_date_estimated"] = False
    out["publication_date_estimated"] = out["publication_date_estimated"].fillna(False).astype(bool)
    if "observation_date" not in out.columns and "period_end" in out.columns:
        out["observation_date"] = out["period_end"]
    # A value we hold today was published no later than today: clip estimated release dates.
    if "publication_date" in out.columns:
        pub = pd.to_datetime(out["publication_date"], errors="coerce")
        cap = pd.Timestamp(ctx.retrieval_date)
        est = out["publication_date_estimated"].astype(bool)
        out["publication_date"] = pub.where(~(est & (pub > cap)), cap)
    return out


def ingest_dataset(
    dataset_id: str,
    *,
    options: dict[str, Any] | None = None,
    from_raw: str | None = None,
    fail_on_validation_error: bool = True,
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    http: HttpClient | None = None,
) -> IngestResult:
    """Run one dataset end-to-end and record the outcome in the manifest.

    ``from_raw`` re-parses an existing raw directory (a retrieval date such as
    ``2026-09-20`` or ``latest``) instead of downloading again.
    """
    settings = settings or get_settings()
    paths = paths or get_paths()
    paths.ensure()
    spec = get_spec(dataset_id)
    manifest = ManifestStore(paths)
    started = dt.datetime.now(dt.UTC)
    run_id = new_run_id(spec.id, started)
    retrieval_date = started.date()
    raw_dir = paths.raw_dir(spec.source, spec.id, retrieval_date)
    record = RunRecord(
        run_id=run_id,
        source=spec.source,
        dataset=spec.id,
        started_at=started,
        retrieval_date=retrieval_date,
        schema_version=SCHEMA_VERSION,
        normalized_table=spec.normalized_table,
        options=dict(options or {}),
    )
    result = IngestResult(dataset_id=spec.id, run_id=run_id, status="running", raw_dir=raw_dir)
    log.info("ingest start", extra={"run_id": run_id, "dataset": spec.id, "source": spec.source})

    if not spec.runnable:
        record.status = "skipped"
        record.error = f"dataset status is {spec.status}; no connector"
        record.completed_at = dt.datetime.now(dt.UTC)
        manifest.append(record)
        result.status = "skipped"
        result.error = record.error
        log.warning(
            "ingest skipped", extra={"run_id": run_id, "dataset": spec.id, "reason": record.error}
        )
        return result

    if spec.requires_api_key and not settings.has_key(spec.requires_api_key):
        record.status = "failed"
        record.error = f"{spec.requires_api_key} not configured"
        record.completed_at = dt.datetime.now(dt.UTC)
        manifest.append(record)
        result.status = "failed"
        result.error = record.error
        log.error(
            "ingest blocked", extra={"run_id": run_id, "dataset": spec.id, "reason": record.error}
        )
        return result

    own_http = http is None
    http = http or HttpClient(settings)
    ctx = IngestContext(
        settings=settings,
        paths=paths,
        http=http,
        run_id=run_id,
        retrieval_date=retrieval_date,
        raw_dir=raw_dir,
        options=dict(options or {}),
    )
    connector = spec.load_connector()
    record.parser_version = connector.parser_version
    try:
        # ---------------------------------------------------------- fetch
        if from_raw:
            source_dir = _resolve_raw_dir(paths, spec, from_raw)
            ctx.raw_dir = source_dir
            ctx.retrieval_date = dt.date.fromisoformat(source_dir.name)
            artifacts = connector.existing_artifacts(source_dir)
            ctx.note(f"re-parsing {len(artifacts)} existing raw artifacts from {source_dir}")
        else:
            artifacts = connector.fetch(ctx)
        result.artifacts = artifacts
        record.artifacts = [a.to_dict() for a in artifacts]
        record.request_params = (
            {k: v for a in artifacts for k, v in a.to_dict()["params"].items()} if artifacts else {}
        )
        if artifacts:
            record.source_url = artifacts[0].url
            record.raw_path = str(ctx.raw_dir)
            record.checksum = (
                artifacts[0].sha256 if len(artifacts) == 1 else _combined_checksum(artifacts)
            )
        # -------------------------------------------------------- staging
        staging = connector.staging_frame(artifacts, ctx)
        if staging is not None and not staging.empty:
            write_parquet_atomic(staging, paths.staging_file(spec.id, ctx.retrieval_date))
        # ---------------------------------------------------------- parse
        parsed = connector.parse(artifacts, ctx)
        if parsed is None or parsed.empty:
            raise DatasetUnavailableError(f"{spec.id}: parser produced no rows")
        schema = SCHEMAS[spec.normalized_table]
        normalized = _add_provenance(parsed, spec, ctx, artifacts)
        normalized = enforce_schema(normalized, schema)
        normalized, dropped = _dedupe(normalized, schema.key)
        if dropped:
            ctx.note(f"dropped {dropped} duplicate rows on natural key {schema.key}")
        # ------------------------------------------------------- validate
        report = validate_table(
            spec.normalized_table, normalized, dataset=spec.id, source=spec.source
        )
        result.validation = report
        record.validation_errors = len(report.errors)
        record.validation_warnings = len(report.warnings)
        record.validation_issues = [i.__dict__ for i in report.issues[:200]]
        for issue in report.issues:
            log.log(
                40 if issue.severity == "error" else 30,
                "validation issue",
                extra={
                    "run_id": run_id,
                    "rule": issue.rule,
                    "field": issue.field,
                    "detail": issue.message,
                },
            )
        previous = manifest.last_success(spec.id)
        prev_rows = (
            int(previous["row_count"])
            if previous is not None and pd.notna(previous["row_count"])
            else None
        )
        warn = compare_row_counts(prev_rows, len(normalized))
        if warn:
            ctx.note(warn)
        if report.errors and fail_on_validation_error:
            raise ValidationError(
                f"{spec.id}: {len(report.errors)} validation errors (first: {report.errors[0].message})",
                report=report,
            )
        # ---------------------------------------------------------- write
        processed = write_processed(normalized, spec.normalized_table, spec.id, paths)
        record.processed_path = str(processed)
        record.row_count = int(len(normalized))
        record.status = "success"
        result.status = "success"
        result.rows = int(len(normalized))
        result.processed_path = processed
        log.info(
            "ingest success",
            extra={
                "run_id": run_id,
                "dataset": spec.id,
                "rows": len(normalized),
                "raw": str(ctx.raw_dir),
                "processed": str(processed),
                "validation_errors": len(report.errors),
                "validation_warnings": len(report.warnings),
            },
        )
    except ElectionDataError as exc:
        record.status = "failed"
        record.error = f"{type(exc).__name__}: {exc}"
        result.status = "failed"
        result.error = record.error
        log.error(
            "ingest failed", extra={"run_id": run_id, "dataset": spec.id, "error": record.error}
        )
    except Exception as exc:  # noqa: BLE001 - record unexpected failures too
        record.status = "failed"
        record.error = f"{type(exc).__name__}: {exc}"
        record.notes.append(traceback.format_exc(limit=8))
        result.status = "failed"
        result.error = record.error
        log.exception("ingest crashed", extra={"run_id": run_id, "dataset": spec.id})
    finally:
        record.completed_at = dt.datetime.now(dt.UTC)
        record.notes.extend(ctx.notes)
        result.notes = list(ctx.notes)
        manifest.append(record)
        if own_http:
            http.close()
    return result


def _combined_checksum(artifacts: list[RawArtifact]) -> str:
    import hashlib

    h = hashlib.sha256()
    for a in sorted(artifacts, key=lambda a: a.path.name):
        h.update(a.sha256.encode())
    return h.hexdigest()


def _resolve_raw_dir(paths: DataPaths, spec: SourceSpec, which: str) -> Path:
    base = paths.raw_dataset_dir(spec.source, spec.id)
    if which == "latest":
        candidates = sorted(p for p in base.glob("*") if p.is_dir() and p.name != "manual")
        if not candidates:
            raise DatasetUnavailableError(f"no raw directories under {base}")
        return candidates[-1]
    target = base / which
    if not target.exists():
        raise DatasetUnavailableError(f"raw directory {target} does not exist")
    return target


def ingest_many(
    dataset_ids: list[str],
    *,
    options: dict[str, Any] | None = None,
    stop_on_error: bool = False,
    **kwargs: Any,
) -> list[IngestResult]:
    results: list[IngestResult] = []
    for did in dataset_ids:
        res = ingest_dataset(did, options=options, **kwargs)
        results.append(res)
        if stop_on_error and not res.ok:
            break
    return results


def ingest_phase(phase: Phase | int | str, **kwargs: Any) -> list[IngestResult]:
    specs = [s for s in list_specs(phase=phase) if s.runnable and s.status != Status.MANUAL]
    return ingest_many([s.id for s in specs], **kwargs)


def update_all(*, include_manual: bool = False, **kwargs: Any) -> list[IngestResult]:
    """Ingest every dataset that can run automatically (DONE/PARTIAL and BLOCKED-with-key)."""
    settings = kwargs.get("settings") or get_settings()
    ids = []
    for s in list_specs(runnable_only=True):
        if s.status == Status.MANUAL and not include_manual:
            continue
        if s.requires_api_key and not settings.has_key(s.requires_api_key):
            log.warning(
                "skipping dataset: missing key", extra={"dataset": s.id, "key": s.requires_api_key}
            )
            continue
        ids.append(s.id)
    return ingest_many(ids, **kwargs)


__all__ = [
    "AuthenticationError",
    "IngestResult",
    "ingest_dataset",
    "ingest_many",
    "ingest_phase",
    "update_all",
]
