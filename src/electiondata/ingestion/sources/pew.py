"""Pew Religious Landscape Study — manual CSV adapter.

Pew publishes state tables on its website and microdata behind a registered
login, so the platform cannot fetch them automatically. Transcribe or compute
state-level shares into ``data/raw/pew/pew-religion/manual/religion.csv`` with
columns ``state, survey_year, publication_date`` plus any of the ``pct_*``
columns of the ``religion`` schema (values 0-100 or 0-1).
"""

from __future__ import annotations

import pandas as pd

from ...exceptions import SchemaChangeError
from ...geo import add_state_columns
from ...quality.schemas import RELIGION
from ..base import IngestContext, ManualFileConnector, RawArtifact
from .polling import _read_manual_csvs, _share


class ReligionConnector(ManualFileConnector):
    dataset_id = "pew-religion"
    expected_files = ("religion.csv",)

    def parse(self, artifacts: list[RawArtifact], ctx: IngestContext) -> pd.DataFrame:
        df = _read_manual_csvs(artifacts)
        missing = {"state", "survey_year", "publication_date"} - set(df.columns)
        if missing:
            raise SchemaChangeError(f"religion CSV missing {sorted(missing)}")
        st = add_state_columns(df, "state")
        if st["state"].isna().any():
            raise SchemaChangeError(f"unmapped states: {df.loc[st['state'].isna(), 'state'].unique()[:5]}")
        out = pd.DataFrame(
            {
                "state": st["state"],
                "state_fips": st["state_fips"],
                "state_name": st["state_name"],
                "survey_year": pd.to_numeric(df["survey_year"], errors="coerce"),
            }
        )
        for col in RELIGION.columns:
            if col.name.startswith("pct_"):
                out[col.name] = _share(df[col.name]) if col.name in df else pd.NA
        out["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
        out["publication_date_estimated"] = False
        out["observation_date"] = out["survey_year"].map(lambda y: pd.Timestamp(int(y), 12, 31))
        out["period_start"] = out["survey_year"].map(lambda y: pd.Timestamp(int(y), 1, 1))
        out["period_end"] = out["observation_date"]
        out["source_url"] = df.get("source_url")
        out["revision_vintage"] = out["survey_year"].astype(str)
        return out
