"""``ed.features`` — modelling-ready datasets with explicit point-in-time cut-offs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from ..quality.point_in_time import DateLike
from ..transform.features import FeatureBuild, audit_features, build_features, load_features
from ._common import norm_office, norm_states


def build(
    year: int,
    office: str,
    as_of: DateLike | None = None,
    *,
    state: str | Sequence[str] | None = None,
    write: bool = True,
    return_build: bool = False,
) -> pd.DataFrame | FeatureBuild:
    """Build state × year × office features using only data published by ``as_of``.

    Returns a DataFrame by default; ``return_build=True`` returns the
    :class:`FeatureBuild` (frame + provenance metadata + path).
    """
    fb = build_features(year, norm_office(office), as_of, states=norm_states(state), write=write)
    return fb if return_build else fb.frame


def load(path: str | Path) -> pd.DataFrame:
    return load_features(path)


def audit(year: int, office: str, as_of: DateLike | None = None) -> dict:
    """Point-in-time audit of a feature build (families, publication cut-offs, leakage flags)."""
    fb = build_features(year, norm_office(office), as_of, write=False, strict=False)
    return audit_features(fb)


__all__ = ["FeatureBuild", "audit", "build", "load"]
