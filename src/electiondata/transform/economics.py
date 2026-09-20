"""Economic features: labour-market snapshots, changes, industry shares, state economy, national series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..quality.point_in_time import DateLike, filter_as_of, latest_as_of, to_date


def _month_floor(d: DateLike) -> pd.Timestamp:
    return pd.Timestamp(to_date(d)).to_period("M").to_timestamp()


def unemployment_features(
    labor: pd.DataFrame, as_of: DateLike, *, seasonally_adjusted: bool = True
) -> pd.DataFrame:
    """Per state: latest month available as of ``as_of`` plus 3m/12m changes and
    12-month averages/employment growth, all computed from months published by ``as_of``.
    """
    df = (
        labor[labor["seasonally_adjusted"] == seasonally_adjusted]
        if "seasonally_adjusted" in labor.columns
        else labor
    )
    avail = filter_as_of(df, as_of).copy()
    if avail.empty:
        return pd.DataFrame(columns=["state", "labor_month", "unemployment_rate"])
    avail["date"] = pd.to_datetime(avail["date"])
    avail = avail.sort_values(["state", "date"])
    rows = []
    for state, g in avail.groupby("state"):
        g = g.drop_duplicates("date").set_index("date").sort_index()
        last = g.index.max()
        ur = g["unemployment_rate"].astype("float64")
        emp = g["employment"].astype("float64")
        lf = g["labor_force"].astype("float64")

        def at(series: pd.Series, months_back: int, _last: pd.Timestamp = last) -> float:
            target = _last - pd.DateOffset(months=months_back)
            return float(series.get(target, np.nan))

        rows.append(
            {
                "state": state,
                "labor_month": last,
                "unemployment_rate": float(ur.iloc[-1]),
                "unemployment_rate_3m_avg": float(ur.iloc[-3:].mean()) if len(ur) >= 3 else np.nan,
                "unemployment_rate_12m_avg": float(ur.iloc[-12:].mean())
                if len(ur) >= 12
                else np.nan,
                "unemployment_change_3m": float(ur.iloc[-1]) - at(ur, 3),
                "unemployment_change_12m": float(ur.iloc[-1]) - at(ur, 12),
                "employment_growth_12m": float(emp.iloc[-1]) / at(emp, 12) - 1
                if at(emp, 12)
                else np.nan,
                "labor_force_growth_12m": float(lf.iloc[-1]) / at(lf, 12) - 1
                if at(lf, 12)
                else np.nan,
                "labor_publication_date": g["publication_date"].max(),
            }
        )
    return pd.DataFrame(rows)


INDUSTRY_SHARE_CODES = {
    # supersectors (agglvl 53, private ownership 5)
    "1011": "pct_natural_resources_mining",
    "1012": "pct_construction",
    "1013": "pct_manufacturing",
    "1021": "pct_trade_transportation_utilities",
    "1022": "pct_information",
    "1023": "pct_finance",
    "1024": "pct_professional_services",
    "1025": "pct_education_health",
    "1026": "pct_hospitality",
    "1027": "pct_other_services",
    # NAICS sectors (agglvl 54)
    "11": "pct_agriculture",
    "21": "pct_mining",
    "44-45": "pct_retail",
    "48-49": "pct_transportation",
    "61": "pct_education",
    "62": "pct_healthcare",
}


def industry_shares(industry: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Employment shares by industry (private ownership) plus government share and wages,
    for the latest year published as of ``as_of``."""
    avail = filter_as_of(industry, as_of)
    if avail.empty:
        return pd.DataFrame(columns=["state", "industry_year"])
    latest_year = int(avail["year"].max())
    y = avail[avail["year"] == latest_year]
    total = y[(y["industry_code"] == "10") & (y["own_code"] == "0")].set_index("state")
    out = pd.DataFrame(
        {
            "state": total.index,
            "industry_year": latest_year,
            "total_employment": total["annual_avg_employment"].values,
            "average_weekly_wage": total["annual_avg_weekly_wage"].values,
            "avg_annual_pay": total["avg_annual_pay"].values,
        }
    )
    out = out.set_index("state")
    private = y[y["own_code"] == "5"]
    for code, name in INDUSTRY_SHARE_CODES.items():
        sub = (
            private[private["industry_code"] == code]
            .groupby("state")["annual_avg_employment"]
            .sum(min_count=1)
        )
        out[name] = sub.reindex(out.index) / out["total_employment"]
    gov = (
        y[(y["industry_code"] == "10") & (y["own_code"].isin(["1", "2", "3"]))]
        .groupby("state")["annual_avg_employment"]
        .sum(min_count=1)
    )
    out["pct_government"] = gov.reindex(out.index) / out["total_employment"]
    return out.reset_index()


def state_economy_features(state_economy: pd.DataFrame, as_of: DateLike) -> pd.DataFrame:
    """Latest annual BEA values as of ``as_of`` with growth rates (real GDP, personal income)."""
    avail = filter_as_of(state_economy, as_of)
    if avail.empty:
        return pd.DataFrame(columns=["state"])
    wide = avail.pivot_table(
        index=["state", "year"], columns="measure", values="value", aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    wide = wide.sort_values(["state", "year"])
    out = wide.groupby("state", as_index=False).tail(1).copy()
    for m in (
        "real_gdp",
        "nominal_gdp",
        "personal_income",
        "real_personal_income",
        "per_capita_personal_income",
    ):
        if m in wide.columns:
            growth = wide.groupby("state")[m].pct_change()
            wide[f"{m}_growth"] = growth
            out[f"{m}_growth"] = wide.loc[out.index, f"{m}_growth"]
    if "real_gdp" in out.columns and "population" in out.columns:
        out["real_gdp_per_capita"] = out["real_gdp"] / out["population"]
    return out.rename(columns={"year": "state_economy_year"}).reset_index(drop=True)


def national_features(national: pd.DataFrame, as_of: DateLike) -> dict[str, float | None]:
    """National economic conditions available as of ``as_of``: unemployment, CPI y/y and 3m annualised,
    payroll growth (1m/3m/12m), average hourly earnings growth."""
    avail = filter_as_of(national, as_of)
    if avail.empty:
        return {}
    avail = avail.copy()
    avail["date"] = pd.to_datetime(avail["date"])
    out: dict[str, float | None] = {}

    def series(measure: str, sa: bool | None = True) -> pd.Series:
        sub = avail[avail["measure"] == measure]
        if sa is not None and "seasonally_adjusted" in sub.columns:
            sel = sub[sub["seasonally_adjusted"] == sa]
            sub = sel if not sel.empty else sub
        return sub.drop_duplicates("date").set_index("date")["value"].astype("float64").sort_index()

    def latest(s: pd.Series) -> float | None:
        return float(s.iloc[-1]) if len(s) else None

    def change(s: pd.Series, months: int, pct: bool = True) -> float | None:
        if len(s) == 0:
            return None
        last = s.index.max()
        prev = s.get(last - pd.DateOffset(months=months))
        if prev is None or pd.isna(prev):
            return None
        return float(s.iloc[-1] / prev - 1) if pct else float(s.iloc[-1] - prev)

    ur = series("unemployment_rate")
    out["national_unemployment_rate"] = latest(ur)
    out["national_unemployment_change_12m"] = change(ur, 12, pct=False)
    out["national_labor_force_participation"] = latest(series("labor_force_participation_rate"))
    cpi = series("cpi_all_items", sa=False)
    out["cpi_yoy"] = change(cpi, 12)
    cpi_sa = series("cpi_all_items", sa=True)
    out["cpi_mom"] = change(cpi_sa, 1)
    c3 = change(cpi_sa, 3)
    out["cpi_3m_annualized"] = (1 + c3) ** 4 - 1 if c3 is not None else None
    out["core_cpi_yoy"] = change(series("cpi_core", sa=False), 12)
    pay = series("nonfarm_payrolls")
    out["nonfarm_payrolls"] = latest(pay)
    out["payroll_growth_1m"] = change(pay, 1)
    out["payroll_growth_3m"] = change(pay, 3)
    out["payroll_growth_12m"] = change(pay, 12)
    ahe = series("average_hourly_earnings")
    out["wage_growth_12m"] = change(ahe, 12)
    if out.get("wage_growth_12m") is not None and out.get("cpi_yoy") is not None:
        out["real_wage_growth_12m"] = (1 + out["wage_growth_12m"]) / (1 + out["cpi_yoy"]) - 1
    out["national_data_month"] = str(avail["date"].max().date())
    return out


def latest_labor_month(labor: pd.DataFrame, as_of: DateLike) -> pd.Timestamp | None:
    avail = latest_as_of(labor, as_of, keys=["state"], order_col="date")
    return pd.to_datetime(avail["date"]).max() if not avail.empty else None
