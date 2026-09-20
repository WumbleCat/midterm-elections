"""electiondata — point-in-time-correct U.S. election data platform.

    import electiondata as ed

    ed.elections.results(year=2024, office="senate", state="PA")
    ed.economics.labor(state="PA", as_of="2024-10-01")
    ed.features.build(year=2024, office="senate", as_of="2024-10-15")

Every query accepts ``as_of`` to restrict rows to those published on or before
that date. See docs/PACKAGE_API.md.
"""

from __future__ import annotations

from . import geo
from .api import candidates, demographics, economics, elections, features, polls
from .config import PACKAGE_VERSION as __version__
from .config import get_settings
from .exceptions import ElectionDataError
from .ingestion.registry import REGISTRY, get_spec, list_specs
from .ingestion.runner import ingest_dataset, ingest_many, ingest_phase, update_all
from .quality.point_in_time import filter_as_of
from .storage.duckdb import query, rebuild_database
from .storage.manifests import ManifestStore
from .storage.parquet import read_table


def runs(dataset: str | None = None, limit: int | None = 50):
    """Ingestion manifest (most recent first)."""
    return ManifestStore().runs(dataset=dataset, limit=limit)


def sources():
    """Source registry as a DataFrame."""
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "id": s.id,
                "source": s.source,
                "dataset": s.dataset_name,
                "phase": int(s.phase),
                "status": s.status.value,
                "access": s.access_method.value,
                "requires_api_key": s.requires_api_key,
                "table": s.normalized_table,
                "frequency": s.frequency,
            }
            for s in list_specs()
        ]
    )


__all__ = [
    "REGISTRY",
    "ElectionDataError",
    "ManifestStore",
    "__version__",
    "candidates",
    "demographics",
    "economics",
    "elections",
    "features",
    "filter_as_of",
    "geo",
    "get_settings",
    "get_spec",
    "ingest_dataset",
    "ingest_many",
    "ingest_phase",
    "list_specs",
    "polls",
    "query",
    "read_table",
    "rebuild_database",
    "runs",
    "sources",
    "update_all",
]
