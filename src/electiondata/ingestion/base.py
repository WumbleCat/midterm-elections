"""Connector interface shared by every source.

A connector does exactly two things:

* :meth:`Connector.fetch` downloads raw artifacts into the run's immutable raw
  directory (through :meth:`IngestContext.download`, which records checksums
  and never overwrites an existing different file);
* :meth:`Connector.parse` turns those artifacts into rows of the connector's
  canonical table (``spec.normalized_table``) **without** provenance columns —
  the runner adds ``source``, ``retrieval_date``, ``ingestion_run_id``, etc.

Connectors set ``publication_date`` (and ``publication_date_estimated``) and
``observation_date`` themselves because only they know the release semantics.
"""

from __future__ import annotations

import datetime as dt
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings
from ..exceptions import AuthenticationError
from ..http import DownloadResult, HttpClient, redact_params, sha256_of_file
from ..logging import get_logger
from ..paths import DataPaths

log = get_logger("ingestion")


@dataclass
class RawArtifact:
    """One immutable raw file plus how it was obtained."""

    path: Path
    url: str
    sha256: str
    size_bytes: int
    params: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None
    content_type: str | None = None
    reused: bool = False  # identical artifact already existed
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "url": self.url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "params": redact_params(self.params),
            "http_status": self.http_status,
            "content_type": self.content_type,
            "reused": self.reused,
            "note": self.note,
            **({"extra": self.extra} if self.extra else {}),
        }


@dataclass
class IngestContext:
    settings: Settings
    paths: DataPaths
    http: HttpClient
    run_id: str
    retrieval_date: dt.date
    raw_dir: Path
    options: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def option(self, key: str, default: Any = None) -> Any:
        value = self.options.get(key)
        return default if value is None else value

    def require_key(self, env_var: str) -> str:
        key = self.settings.key_for(env_var)
        if not key:
            raise AuthenticationError(
                f"{env_var} is not set; this dataset requires an API key (see .env.example)"
            )
        return key

    def note(self, message: str) -> None:
        self.notes.append(message)
        log.info(message, extra={"run_id": self.run_id})

    def target_path(self, filename: str) -> Path:
        return self.raw_dir / filename

    def download(
        self,
        url: str,
        filename: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        json: Any = None,
        note: str = "",
    ) -> RawArtifact:
        """Download into the raw dir without ever overwriting a different existing file."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        dest = self.target_path(filename)
        staging = dest.with_name(dest.name + ".download")
        result: DownloadResult = self.http.download(
            url, staging, params=params, headers=headers, method=method, json=json
        )
        final, reused = _place_immutably(staging, dest, result.sha256)
        artifact = RawArtifact(
            path=final,
            url=result.requested_url,  # stable URL; redirect targets may carry signed params
            sha256=result.sha256,
            size_bytes=result.size_bytes,
            params=dict(params or {}),
            http_status=result.status_code,
            content_type=result.content_type,
            reused=reused,
            note=note,
            extra={"final_url": result.url.split("?")[0]} if result.url != result.requested_url else {},
        )
        log.info(
            "raw artifact stored",
            extra={
                "run_id": self.run_id,
                "url": result.requested_url,
                "path": str(final),
                "bytes": result.size_bytes,
                "sha256": result.sha256[:12],
                "reused": reused,
            },
        )
        return artifact

    def write_bytes(self, data: bytes, filename: str, *, url: str, params: dict[str, Any] | None = None, http_status: int | None = None, note: str = "") -> RawArtifact:
        """Store an in-memory payload (e.g. an API JSON response) as a raw artifact."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        dest = self.target_path(filename)
        staging = dest.with_name(dest.name + ".download")
        staging.write_bytes(data)
        digest = sha256_of_file(staging)
        final, reused = _place_immutably(staging, dest, digest)
        return RawArtifact(
            path=final,
            url=url,
            sha256=digest,
            size_bytes=len(data),
            params=dict(params or {}),
            http_status=http_status,
            reused=reused,
            note=note,
        )


def _place_immutably(staging: Path, dest: Path, digest: str) -> tuple[Path, bool]:
    """Move ``staging`` to ``dest`` unless an identical file exists; never overwrite a different one."""
    if dest.exists():
        if sha256_of_file(dest) == digest:
            staging.unlink(missing_ok=True)
            return dest, True
        stamp = dt.datetime.now().strftime("%H%M%S")
        alt = dest.with_name(f"{dest.stem}.{stamp}{dest.suffix}")
        shutil.move(str(staging), str(alt))
        return alt, False
    shutil.move(str(staging), str(dest))
    return dest, False


class Connector(ABC):
    """Base class for all connectors. Subclasses set ``dataset_id`` to a registry id."""

    dataset_id: str
    parser_version: str = "1"

    @abstractmethod
    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        """Download raw artifacts for this run."""

    @abstractmethod
    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        """Parse artifacts into canonical rows (no provenance columns)."""

    def staging_frame(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame | None:
        """Optional: the as-received tabular form, saved under data/staging for debugging."""
        return None

    def existing_artifacts(self, raw_dir: Path) -> list[RawArtifact]:
        """Rebuild artifact objects from a previous raw directory (for ``--from-raw``)."""
        out = []
        for p in sorted(raw_dir.iterdir()):
            if p.is_file() and not p.name.endswith((".part", ".download", ".tmp")):
                out.append(RawArtifact(path=p, url="", sha256=sha256_of_file(p), size_bytes=p.stat().st_size, reused=True))
        return out


class ManualFileConnector(Connector):
    """Connector for datasets that must be downloaded by hand (login-gated, licence-gated).

    The user drops the file(s) into ``data/raw/{source}/{dataset}/manual/`` and
    the connector parses them. ``fetch`` never touches the network.
    """

    manual_subdir: str = "manual"
    expected_files: tuple[str, ...] = ()

    def fetch(self, ctx: IngestContext) -> list[RawArtifact]:
        manual_dir = ctx.raw_dir.parent / self.manual_subdir
        if not manual_dir.exists() or not any(manual_dir.iterdir()):
            from ..exceptions import DatasetUnavailableError

            raise DatasetUnavailableError(
                f"manual dataset: place {', '.join(self.expected_files) or 'the source file(s)'} in {manual_dir}"
            )
        artifacts = []
        for p in sorted(manual_dir.iterdir()):
            if p.is_file():
                artifacts.append(
                    RawArtifact(
                        path=p,
                        url=f"manual://{p.name}",
                        sha256=sha256_of_file(p),
                        size_bytes=p.stat().st_size,
                        reused=True,
                        note="manually supplied file",
                    )
                )
        return artifacts
