"""Generate the machine-verifiable parts of the documentation.

``docs/STATUS.md``, ``docs/DATA_MODEL.md`` and ``docs/DATA_SOURCES.md`` contain
blocks delimited by ``<!-- BEGIN GENERATED:name -->`` / ``<!-- END GENERATED:name -->``
that are rewritten from the source registry, the table schemas and the
ingestion manifest. Text outside the markers is hand-curated and preserved.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .config import _find_project_root
from .ingestion.registry import REGISTRY, Status, list_specs, status_counts
from .paths import DataPaths, get_paths
from .quality.schemas import SCHEMAS
from .storage.manifests import ManifestStore
from .storage.parquet import table_inventory


def docs_dir() -> Path:
    root = _find_project_root() or Path.cwd()
    return root / "docs"


def _fmt_ts(value: object) -> str:
    if (
        value is None
        or (isinstance(value, float) and pd.isna(value))
        or value is pd.NaT
        or value is pd.NA
    ):
        return "-"
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return str(value)


def status_frame(paths: DataPaths | None = None) -> pd.DataFrame:
    """Registry joined with the manifest: one row per dataset."""
    paths = paths or get_paths()
    latest = (
        ManifestStore(paths).latest_by_dataset().set_index("dataset")
        if paths.manifest_file.exists()
        else pd.DataFrame()
    )
    inventory = table_inventory(paths)
    rows = []
    for s in list_specs():
        m = latest.loc[s.id] if not latest.empty and s.id in latest.index else None
        inv = inventory[inventory["dataset_id"] == s.id]
        rows.append(
            {
                "phase": int(s.phase),
                "source": s.source,
                "dataset_id": s.id,
                "dataset": s.dataset_name,
                "table": s.normalized_table,
                "status": s.status.value,
                "tested": "yes" if s.tested else "no",
                "requires_key": s.requires_api_key or "",
                "last_run_status": (m["last_status"] if m is not None else None),
                "last_run": _fmt_ts(m["last_run"]) if m is not None else "-",
                "last_success": _fmt_ts(m["last_success"]) if m is not None else "-",
                "rows": int(inv["rows"].sum()) if not inv.empty else None,
                "last_error": (
                    str(m["last_error"])[:120]
                    if m is not None and pd.notna(m["last_error"])
                    else ""
                ),
                "notes": s.known_limitations,
            }
        )
    return pd.DataFrame(rows)


def status_markdown(paths: DataPaths | None = None) -> str:
    df = status_frame(paths)
    counts = status_counts()
    lines = [
        f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} from the source registry and `data/manifests/ingestion_runs.parquet`. Do not edit inside the markers; run `electiondata status --write-docs`._",
        "",
        "```",
        *[f"{k}: {v}" for k, v in counts.items()],
        "```",
        "",
        "| Phase | Source | Dataset id | Table | Status | Tested | Last successful pull | Rows | Last run | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        has_run = r["last_run_status"] is not None and pd.notna(r["last_run_status"])
        last_run = f"{r['last_run']} ({r['last_run_status']})" if has_run else "-"
        note = r["notes"].replace("|", "/")
        if r["last_error"]:
            note = f"**last error:** {r['last_error'].replace('|', '/')} — {note}"
        rows_txt = "" if r["rows"] is None or pd.isna(r["rows"]) else f"{int(r['rows']):,}"
        lines.append(
            f"| {r['phase']} | {r['source']} | `{r['dataset_id']}` | `{r['table']}` | {r['status']} | {r['tested']} | {r['last_success']} | {rows_txt} | {last_run} | {note} |"
        )
    return "\n".join(lines)


def data_model_markdown() -> str:
    out = [
        f"_Generated {dt.datetime.now():%Y-%m-%d} from `electiondata.quality.schemas`. Run `electiondata docs` to refresh._",
        "",
    ]
    for schema in SCHEMAS.values():
        out.append(f"### `{schema.name}`")
        out.append("")
        out.append(schema.description)
        out.append("")
        out.append(f"* **Frequency:** {schema.frequency}")
        out.append(f"* **Natural key:** `{', '.join(schema.key)}`")
        out.append(
            f"* **Kind:** {'derived (transform output)' if schema.derived else 'ingested (normalized)'}"
        )
        out.append(f"* **Provenance columns:** {'yes (see below)' if schema.provenance else 'no'}")
        for n in schema.notes:
            out.append(f"* **Note:** {n}")
        out.append("")
        out.append("| Column | Type | Nullable | Unit | Description |")
        out.append("|---|---|---|---|---|")
        for c in schema.columns:
            out.append(
                f"| `{c.name}` | {c.dtype} | {'yes' if c.nullable else 'no'} | {c.unit} | {c.description} |"
            )
        out.append("")
    from .quality.schemas import PROVENANCE_COLUMNS

    out.append("### Provenance columns (every ingested table)")
    out.append("")
    out.append("| Column | Type | Nullable | Description |")
    out.append("|---|---|---|---|")
    for c in PROVENANCE_COLUMNS:
        out.append(
            f"| `{c.name}` | {c.dtype} | {'yes' if c.nullable else 'no'} | {c.description} |"
        )
    return "\n".join(out)


def data_sources_markdown() -> str:
    out = [
        f"_Generated {dt.datetime.now():%Y-%m-%d} from the source registry. Hand-written notes live outside the markers._",
        "",
    ]
    for s in list_specs():
        out.append(f"### {s.source_name} — {s.dataset_name}")
        out.append("")
        out.append(f"* **Dataset id:** `{s.id}` (phase {int(s.phase)})")
        out.append(f"* **Status:** {s.status.value}{' — tested with fixtures' if s.tested else ''}")
        out.append(f"* **Authoritative URL:** {s.authoritative_url}")
        out.append(f"* **Access method:** {s.access_method.value}")
        out.append(f"* **Credentials:** {s.requires_api_key or 'none'}")
        out.append(f"* **Frequency / geography:** {s.frequency}; {s.geography}")
        out.append(f"* **Update frequency:** {s.update_frequency or '-'}")
        out.append(
            f"* **Raw table:** `{s.raw_table or '-'}` → **normalized table:** `{s.normalized_table}`"
        )
        out.append(f"* **Variables:** {', '.join(f'`{v}`' for v in s.variables) or '-'}")
        if s.options:
            out.append(
                "* **Ingest options:** " + "; ".join(f"`{k}`: {v}" for k, v in s.options.items())
            )
        out.append(f"* **Description:** {s.description}")
        out.append(f"* **Known limitations:** {s.known_limitations or '-'}")
        out.append("")
    return "\n".join(out)


_MARKER = "<!-- {kind} GENERATED:{name} -->"


def update_between_markers(path: Path, name: str, content: str) -> bool:
    """Replace the block between BEGIN/END markers; append the block if missing."""
    begin = _MARKER.format(kind="BEGIN", name=name)
    end = _MARKER.format(kind="END", name=name)
    block = f"{begin}\n{content}\n{end}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        if pattern.search(text):
            new_text = pattern.sub(lambda _m: block, text)
        else:
            new_text = text.rstrip("\n") + "\n\n" + block + "\n"
    else:
        new_text = block + "\n"
    changed = not path.exists() or new_text != path.read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return changed


def write_generated_docs(
    paths: DataPaths | None = None,
    *,
    which: tuple[str, ...] = ("status", "data_model", "data_sources"),
) -> list[Path]:
    d = docs_dir()
    written = []
    if "status" in which:
        update_between_markers(d / "STATUS.md", "status", status_markdown(paths))
        written.append(d / "STATUS.md")
    if "data_model" in which:
        update_between_markers(d / "DATA_MODEL.md", "data_model", data_model_markdown())
        written.append(d / "DATA_MODEL.md")
    if "data_sources" in which:
        update_between_markers(d / "DATA_SOURCES.md", "data_sources", data_sources_markdown())
        written.append(d / "DATA_SOURCES.md")
    return written


def known_broken(paths: DataPaths | None = None) -> list[str]:
    df = status_frame(paths)
    bad = df[
        (df["last_run_status"] == "failed")
        & df["status"].isin([Status.DONE.value, Status.PARTIAL.value])
    ]
    return bad["dataset_id"].tolist()


__all__ = [
    "REGISTRY",
    "data_model_markdown",
    "data_sources_markdown",
    "known_broken",
    "status_frame",
    "status_markdown",
    "update_between_markers",
    "write_generated_docs",
]
