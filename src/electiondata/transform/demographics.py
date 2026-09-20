"""Demographic / population / geography features as of a date."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from ..quality.point_in_time import DateLike, filter_as_of, latest_as_of

DEMOGRAPHIC_FEATURES = [
    "median_age",
    "pct_18_24",
    "pct_25_34",
    "pct_35_44",
    "pct_45_54",
    "pct_55_64",
    "pct_65_74",
    "pct_75_plus",
    "pct_65_plus",
    "pct_less_than_high_school",
    "pct_high_school",
    "pct_some_college",
    "pct_associate_degree",
    "pct_bachelors",
    "pct_graduate_degree",
    "pct_bachelors_or_higher",
    "median_household_income",
    "per_capita_income",
    "mean_household_income",
    "poverty_rate",
    "gini_coefficient",
    "pct_white_non_hispanic",
    "pct_black",
    "pct_hispanic_latino",
    "pct_asian",
    "pct_native_american",
    "pct_multiracial",
    "pct_native_born",
    "pct_naturalized_citizen",
    "pct_non_citizen",
    "pct_foreign_born",
    "citizen_voting_age_population",
]


def demographics_as_of(
    demographics: pd.DataFrame, as_of: DateLike, *, survey: str = "acs1"
) -> pd.DataFrame:
    """Latest ACS profile per state published on or before ``as_of``."""
    df = (
        demographics[demographics["survey"] == survey]
        if "survey" in demographics.columns
        else demographics
    )
    latest = latest_as_of(df, as_of, keys=["state"], order_col="year")
    if latest.empty:
        return latest
    cols = [
        "state",
        "year",
        "publication_date",
        *[c for c in DEMOGRAPHIC_FEATURES if c in latest.columns],
    ]
    out = latest[cols].rename(
        columns={"year": "acs_year", "publication_date": "acs_publication_date"}
    )
    out["acs_total_population"] = latest["total_population"].values
    return out.reset_index(drop=True)


def population_as_of(population: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Per state: latest available annual population (from the latest vintage published by
    ``as_of``) plus 1-, 4- and 10-year growth computed within that same vintage."""
    avail = filter_as_of(population, as_of)
    if avail.empty:
        return pd.DataFrame(
            columns=[
                "state",
                "population",
                "population_year",
                "population_growth_1y",
                "population_growth_4y",
                "population_growth_10y",
            ]
        )
    avail = avail.copy()
    avail["_v"] = pd.to_numeric(avail["revision_vintage"], errors="coerce")
    # For each state-year keep the newest available vintage, then compute growth on that series.
    series = (
        avail.sort_values(["state", "year", "_v"])
        .groupby(["state", "year"], as_index=False)
        .tail(1)
    )
    series = series.sort_values(["state", "year"])
    g = series.groupby("state")["population"]
    series["population_growth_1y"] = series["population"] / g.shift(1) - 1
    series["population_growth_4y"] = series["population"] / g.shift(4) - 1
    series["population_growth_10y"] = series["population"] / g.shift(10) - 1
    latest = series.groupby("state", as_index=False).tail(1)
    out = latest[
        [
            "state",
            "year",
            "population",
            "population_growth_1y",
            "population_growth_4y",
            "population_growth_10y",
            "domestic_migration",
            "international_migration",
            "net_migration",
            "domestic_migration_rate",
            "net_migration_rate",
            "publication_date",
            "revision_vintage",
        ]
    ].rename(
        columns={
            "year": "population_year",
            "publication_date": "population_publication_date",
            "revision_vintage": "population_vintage",
        }
    )
    return out.reset_index(drop=True)


def density_features(
    pop_features: pd.DataFrame, geography: pd.DataFrame, as_of: DateLike
) -> pd.DataFrame:
    geo = latest_as_of(geography, as_of, keys=["state"], order_col="year")
    if geo.empty or pop_features.empty:
        return pop_features
    out = pop_features.merge(geo[["state", "land_area_sq_miles"]], on="state", how="left")
    out["population_density"] = out["population"] / out["land_area_sq_miles"]
    out["log_population_density"] = np.log1p(out["population_density"])
    return out


def urban_features(urban_rural: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    latest = latest_as_of(urban_rural, as_of, keys=["state"], order_col="year")
    if latest.empty:
        return pd.DataFrame(columns=["state", "pct_urban", "pct_rural", "urban_rural_census_year"])
    return (
        latest[["state", "pct_urban", "pct_rural", "year"]]
        .rename(columns={"year": "urban_rural_census_year"})
        .reset_index(drop=True)
    )


def as_date(value: DateLike) -> dt.date:
    return pd.Timestamp(value).date()
