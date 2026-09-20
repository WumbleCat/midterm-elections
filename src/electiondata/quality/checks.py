"""Data-quality rules for canonical tables.

Every rule produces :class:`ValidationIssue` records that identify the source,
dataset, table, field, record and rule, so failures are actionable. Rules
never drop rows — they report; the caller decides what to do.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from ..geo import is_valid_state, normalize_state
from .schemas import SCHEMAS, TableSchema

Severity = str  # "error" | "warning"


@dataclass(frozen=True)
class ValidationIssue:
    table: str
    dataset: str
    source: str
    rule: str
    severity: Severity
    message: str
    field: str | None = None
    record: str | None = None  # natural-key description of an offending row
    count: int = 1


@dataclass
class ValidationReport:
    table: str
    dataset: str
    rows: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(i) for i in self.issues])

    def summary(self) -> str:
        return (
            f"{self.table}/{self.dataset}: rows={self.rows} errors={len(self.errors)} "
            f"warnings={len(self.warnings)}"
        )


Rule = Callable[[pd.DataFrame, TableSchema, "RuleContext"], Iterable[ValidationIssue]]


@dataclass
class RuleContext:
    table: str
    dataset: str
    source: str
    max_examples: int = 5

    def issue(
        self,
        rule: str,
        severity: Severity,
        message: str,
        *,
        field: str | None = None,
        record: str | None = None,
        count: int = 1,
    ) -> ValidationIssue:
        return ValidationIssue(
            table=self.table,
            dataset=self.dataset,
            source=self.source,
            rule=rule,
            severity=severity,
            message=message,
            field=field,
            record=record,
            count=count,
        )


def _describe_rows(df: pd.DataFrame, idx: pd.Index, key: tuple[str, ...], limit: int) -> str:
    cols = [k for k in key if k in df.columns]
    if not cols:
        return f"{len(idx)} rows"
    sub = df.loc[idx[:limit], cols].map(lambda v: "" if pd.isna(v) else str(v))
    sample = sub.agg("|".join, axis=1).tolist()
    more = "" if len(idx) <= limit else f" (+{len(idx) - limit} more)"
    return ";".join(sample) + more


# ------------------------------------------------------------------ rules


def rule_required_columns(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    for col in schema.all_columns:
        if not col.nullable and col.name not in df.columns:
            yield ctx.issue(
                "required_column_missing", "error", f"column {col.name} missing", field=col.name
            )
        elif not col.nullable and col.name in df.columns and df[col.name].isna().any():
            n = int(df[col.name].isna().sum())
            idx = df.index[df[col.name].isna()]
            yield ctx.issue(
                "required_column_null",
                "error",
                f"{n} null values in required column {col.name}",
                field=col.name,
                record=_describe_rows(df, idx, schema.key, ctx.max_examples),
                count=n,
            )


def rule_unique_key(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    key = [k for k in schema.key if k in df.columns]
    if not key or df.empty:
        return
    dup = df.duplicated(subset=key, keep=False)
    if dup.any():
        n = int(dup.sum())
        yield ctx.issue(
            "duplicate_key",
            "error",
            f"{n} rows share a natural key {key}",
            field=",".join(key),
            record=_describe_rows(df, df.index[dup], schema.key, ctx.max_examples),
            count=n,
        )


def rule_valid_state(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    for col in ("state", "origin_state", "destination_state"):
        if col not in df.columns:
            continue
        values = df[col].dropna()
        bad = values[~values.map(lambda v: is_valid_state(v) or v == "US")]
        if not bad.empty:
            yield ctx.issue(
                "invalid_state",
                "error",
                f"{len(bad)} rows with unmapped state in {col}: {sorted(set(bad.astype(str)))[:10]}",
                field=col,
                count=int(len(bad)),
            )
    if "state" in df.columns and "state_fips" in df.columns:
        both = df[["state", "state_fips"]].dropna()
        mism = both[both["state"].map(normalize_state) != both["state_fips"].map(normalize_state)]
        if not mism.empty:
            yield ctx.issue(
                "state_fips_mismatch",
                "error",
                f"{len(mism)} rows where state and state_fips disagree",
                field="state_fips",
                record=_describe_rows(df, mism.index, schema.key, ctx.max_examples),
                count=int(len(mism)),
            )


def rule_shares_in_unit_interval(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    for col in schema.all_columns:
        if col.name not in df.columns:
            continue
        if col.unit.startswith("share 0-1") or col.unit == "0-1":
            s = pd.to_numeric(df[col.name], errors="coerce")
            bad = s[(s < -1e-9) | (s > 1 + 1e-9)]
            if not bad.empty:
                yield ctx.issue(
                    "share_out_of_range",
                    "error",
                    f"{len(bad)} values of {col.name} outside [0, 1] (min={s.min():.4g}, max={s.max():.4g})",
                    field=col.name,
                    record=_describe_rows(df, bad.index, schema.key, ctx.max_examples),
                    count=int(len(bad)),
                )
        elif col.unit == "percent 0-100":
            s = pd.to_numeric(df[col.name], errors="coerce")
            bad = s[(s < 0) | (s > 100)]
            if not bad.empty:
                yield ctx.issue(
                    "percent_out_of_range",
                    "error",
                    f"{len(bad)} values of {col.name} outside [0, 100]",
                    field=col.name,
                    count=int(len(bad)),
                )


_NONNEGATIVE_UNITS = {"votes", "persons", "ballots", "establishments", "thousands"}


def rule_nonnegative_counts(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    for col in schema.all_columns:
        if col.name in df.columns and col.unit in _NONNEGATIVE_UNITS:
            s = pd.to_numeric(df[col.name], errors="coerce")
            bad = s[s < 0]
            if not bad.empty:
                yield ctx.issue(
                    "negative_count",
                    "error",
                    f"{len(bad)} negative values in {col.name}",
                    field=col.name,
                    record=_describe_rows(df, bad.index, schema.key, ctx.max_examples),
                    count=int(len(bad)),
                )


def rule_dates_parseable(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    for col in schema.all_columns:
        if col.dtype in ("date", "timestamp") and col.name in df.columns:
            raw = df[col.name]
            parsed = pd.to_datetime(raw, errors="coerce")
            bad = raw.notna() & parsed.isna()
            if bad.any():
                yield ctx.issue(
                    "unparseable_date",
                    "error",
                    f"{int(bad.sum())} unparseable values in {col.name}",
                    field=col.name,
                    count=int(bad.sum()),
                )
    if "period_start" in df.columns and "period_end" in df.columns:
        ps = pd.to_datetime(df["period_start"], errors="coerce")
        pe = pd.to_datetime(df["period_end"], errors="coerce")
        bad = (ps > pe).fillna(False)
        if bad.any():
            yield ctx.issue(
                "period_start_after_end",
                "error",
                f"{int(bad.sum())} rows with period_start > period_end",
                field="period_start",
                count=int(bad.sum()),
            )


def rule_publication_after_observation(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    if "publication_date" not in df.columns or "observation_date" not in df.columns:
        return
    pub = pd.to_datetime(df["publication_date"], errors="coerce")
    obs = pd.to_datetime(df["observation_date"], errors="coerce")
    bad = (pub < obs).fillna(False)
    if bad.any():
        yield ctx.issue(
            "publication_before_observation",
            "warning",
            f"{int(bad.sum())} rows published before their observation date (allowed for early estimates)",
            field="publication_date",
            count=int(bad.sum()),
        )
    if schema.provenance and pub.isna().any():
        n = int(pub.isna().sum())
        yield ctx.issue(
            "publication_date_missing",
            "warning",
            f"{n} rows without publication_date; they will be excluded by point-in-time filters",
            field="publication_date",
            count=n,
        )


_CANONICAL_PARTIES = {"DEM", "REP", "LIB", "GRN", "IND", "OTHER"}


def rule_party_canonical(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    if "party" not in df.columns:
        return
    vals = df["party"].dropna()
    bad = vals[~vals.isin(_CANONICAL_PARTIES)]
    if not bad.empty:
        yield ctx.issue(
            "party_not_canonical",
            "error",
            f"{len(bad)} rows with non-canonical party values: {sorted(set(bad))[:10]}",
            field="party",
            count=int(len(bad)),
        )


def rule_vote_reconciliation(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    """dem+rep+other should reconcile with total_candidate_votes; and candidate votes <= total_votes."""
    if schema.name == "election_race_summary":
        parts = ["dem_votes", "rep_votes", "other_votes", "total_candidate_votes"]
        if all(c in df.columns for c in parts):
            s = df[parts].apply(pd.to_numeric, errors="coerce")
            diff = (
                s["dem_votes"].fillna(0) + s["rep_votes"].fillna(0) + s["other_votes"].fillna(0)
            ) - s["total_candidate_votes"]
            bad = diff.abs() > 1
            if bad.any():
                yield ctx.issue(
                    "vote_components_mismatch",
                    "error",
                    f"{int(bad.sum())} races where dem+rep+other != total_candidate_votes",
                    field="total_candidate_votes",
                    record=_describe_rows(df, df.index[bad], schema.key, ctx.max_examples),
                    count=int(bad.sum()),
                )
        if "total_votes" in df.columns and "total_candidate_votes" in df.columns:
            tv = pd.to_numeric(df["total_votes"], errors="coerce")
            tcv = pd.to_numeric(df["total_candidate_votes"], errors="coerce")
            ratio = tcv / tv
            bad = ((ratio > 1.01) | (ratio < 0.9)).fillna(False)
            if bad.any():
                yield ctx.issue(
                    "candidate_votes_vs_total",
                    "warning",
                    f"{int(bad.sum())} races where candidate votes deviate >10% from reported total_votes",
                    field="total_votes",
                    record=_describe_rows(df, df.index[bad], schema.key, ctx.max_examples),
                    count=int(bad.sum()),
                )
    if schema.name == "election_results" and {"votes", "total_votes"} <= set(df.columns):
        v = pd.to_numeric(df["votes"], errors="coerce")
        t = pd.to_numeric(df["total_votes"], errors="coerce")
        bad = (v > t * 1.001 + 1).fillna(False)
        if bad.any():
            yield ctx.issue(
                "candidate_votes_exceed_total",
                "error",
                f"{int(bad.sum())} rows where candidate votes exceed total_votes",
                field="votes",
                record=_describe_rows(df, df.index[bad], schema.key, ctx.max_examples),
                count=int(bad.sum()),
            )


def rule_turnout_consistency(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    if schema.name != "turnout":
        return
    if {"ballots_cast", "registered_voters"} <= set(df.columns):
        b = pd.to_numeric(df["ballots_cast"], errors="coerce")
        r = pd.to_numeric(df["registered_voters"], errors="coerce")
        bad = (b > r * 1.05).fillna(False)
        if bad.any():
            yield ctx.issue(
                "ballots_exceed_registered",
                "warning",
                f"{int(bad.sum())} state-years where ballots_cast exceeds registered_voters by >5% (same-day registration states can legitimately approach 1.0)",
                field="ballots_cast",
                record=_describe_rows(df, df.index[bad], schema.key, ctx.max_examples),
                count=int(bad.sum()),
            )


def rule_share_groups_sum(df: pd.DataFrame, schema: TableSchema, ctx: RuleContext):
    groups = {
        "demographics": [
            [
                "pct_under_18",
                "pct_18_24",
                "pct_25_34",
                "pct_35_44",
                "pct_45_54",
                "pct_55_64",
                "pct_65_74",
                "pct_75_plus",
            ],
            ["pct_male", "pct_female"],
            [
                "pct_less_than_high_school",
                "pct_high_school",
                "pct_some_college",
                "pct_associate_degree",
                "pct_bachelors",
                "pct_graduate_degree",
            ],
        ],
        "urban_rural": [["pct_urban", "pct_rural"]],
    }
    for cols in groups.get(schema.name, []):
        if not all(c in df.columns for c in cols):
            continue
        s = df[cols].apply(pd.to_numeric, errors="coerce")
        complete = s.notna().all(axis=1)
        total = s.sum(axis=1)
        bad = complete & ((total < 0.98) | (total > 1.02))
        if bad.any():
            yield ctx.issue(
                "share_group_sum",
                "warning",
                f"{int(bad.sum())} rows where {cols[0]}.. group does not sum to ~1 (min={total[complete].min():.3f}, max={total[complete].max():.3f})",
                field=cols[0],
                record=_describe_rows(df, df.index[bad], schema.key, ctx.max_examples),
                count=int(bad.sum()),
            )


RULES: tuple[Rule, ...] = (
    rule_required_columns,
    rule_unique_key,
    rule_valid_state,
    rule_shares_in_unit_interval,
    rule_nonnegative_counts,
    rule_dates_parseable,
    rule_publication_after_observation,
    rule_party_canonical,
    rule_vote_reconciliation,
    rule_turnout_consistency,
    rule_share_groups_sum,
)


def validate_table(
    table: str,
    df: pd.DataFrame,
    *,
    dataset: str = "",
    source: str = "",
    rules: Iterable[Rule] = RULES,
) -> ValidationReport:
    schema = SCHEMAS[table]
    ctx = RuleContext(table=table, dataset=dataset, source=source)
    report = ValidationReport(table=table, dataset=dataset, rows=len(df))
    for rule in rules:
        report.issues.extend(rule(df, schema, ctx))
    return report


def compare_row_counts(
    previous: int | None, current: int, *, tolerance: float = 0.25
) -> str | None:
    """Return a warning message when the row count moved suspiciously versus the last run."""
    if previous is None or previous == 0:
        return None
    change = (current - previous) / previous
    if abs(change) > tolerance:
        return f"row count changed {change:+.0%} versus previous run ({previous} -> {current})"
    return None


def audit_frame(df: pd.DataFrame, table: str) -> dict[str, Any]:
    """Quick dataset audit used by the data-quality skill / CLI."""
    schema = SCHEMAS[table]
    key = [k for k in schema.key if k in df.columns]
    missing = df.isna().mean().sort_values(ascending=False)
    return {
        "table": table,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_key_rows": int(df.duplicated(subset=key, keep=False).sum()) if key else None,
        "missingness_top": {k: round(float(v), 3) for k, v in missing.head(10).items()},
        "datasets": sorted(df["dataset_id"].dropna().unique().tolist())
        if "dataset_id" in df
        else [],
        "states": int(df["state"].nunique()) if "state" in df else None,
    }
