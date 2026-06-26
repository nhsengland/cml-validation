"""Validation checks for the Relationships table against the CML Proforma schema."""

import pandas as pd

from validators.base import ValidationResult


EXPECTED_COLUMNS = [
    "metric_id",
    "metric_short_name",
    "child_metric_id",
    "child_metric_short_name",
    "relationship_type",
    "relationship_category",
    "relationship_description",
]

MANDATORY_COLUMNS = [
    "metric_id",
    "child_metric_id",
    "child_metric_short_name",
    "relationship_type",
    "relationship_category",
    "relationship_description",
]

VALID_RELATIONSHIP_TYPES = {
    "Numerator",
    "Denominator",
    "Set Name",
    "Benchmarking",
    "Flag",
    "Replaces",
    "NA",
}

VALID_RELATIONSHIP_CATEGORIES = {"Direct", "Indirect", "NA"}

# metric_id = metric_family_id + "_" + first 3 chars of metric_status.
# Valid statuses: Actual, Estimate, Forecast, Planned, Variance, Complete, Incomplete
VALID_METRIC_ID_SUFFIXES = {"act", "est", "for", "pla", "var", "com", "inc", "prov"}
METRIC_ID_PATTERN = r"^[A-Za-z0-9]+_(" + "|".join(VALID_METRIC_ID_SUFFIXES) + r")$"


def check_expected_columns(df: pd.DataFrame) -> ValidationResult:
    actual = set(df.columns)
    expected = set(EXPECTED_COLUMNS)
    missing = expected - actual
    extra = actual - expected

    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected: {sorted(extra)}")
        return ValidationResult("expected_columns", "fail", "; ".join(parts))
    return ValidationResult("expected_columns", "pass", "All expected columns present")


def check_column_order(df: pd.DataFrame) -> ValidationResult:
    actual = [c for c in df.columns if c in EXPECTED_COLUMNS]
    if actual != EXPECTED_COLUMNS:
        return ValidationResult(
            "column_order", "fail",
            f"Expected order {EXPECTED_COLUMNS}, got {actual}",
        )
    return ValidationResult("column_order", "pass", "Column order matches schema")


def check_no_duplicate_rows(df: pd.DataFrame) -> ValidationResult:
    if "metric_id" not in df.columns or "child_metric_id" not in df.columns:
        return ValidationResult("no_duplicate_rows", "fail", "Required columns missing, skipping")
    dupes = df.duplicated(subset=["metric_id", "child_metric_id"], keep=False)
    if dupes.any():
        return ValidationResult(
            "no_duplicate_rows", "fail",
            f"{dupes.sum()} rows are duplicated on (metric_id, child_metric_id)",
            df.index[dupes],
        )
    return ValidationResult("no_duplicate_rows", "pass", "No duplicate (metric_id, child_metric_id) pairs")


def check_mandatory_not_null(df: pd.DataFrame) -> ValidationResult:
    available = [c for c in MANDATORY_COLUMNS if c in df.columns]
    failures = {
        col: df.index[df[col].isna() | (df[col].astype(str).str.strip() == "")]
        for col in available
        if (df[col].isna() | (df[col].astype(str).str.strip() == "")).any()
    }
    if failures:
        summary = {col: len(idx) for col, idx in failures.items()}
        all_failing = pd.Index(sorted({i for idx in failures.values() for i in idx}))
        return ValidationResult("mandatory_not_null", "fail", f"Null/empty values in mandatory columns: {summary}", all_failing)
    return ValidationResult("mandatory_not_null", "pass", "All mandatory columns populated")


def check_metric_id_format(df: pd.DataFrame) -> ValidationResult:
    if "metric_id" not in df.columns:
        return ValidationResult("metric_id_format", "fail", "metric_id column missing")
    invalid = ~df["metric_id"].astype(str).str.match(METRIC_ID_PATTERN)
    if invalid.any():
        bad_vals = df.loc[invalid, "metric_id"].unique().tolist()
        return ValidationResult(
            "metric_id_format", "fail",
            f"{invalid.sum()} metric_id values have unrecognised suffix. "
            f"Valid suffixes: {sorted(VALID_METRIC_ID_SUFFIXES)}. Got: {bad_vals[:5]}{'...' if len(bad_vals) > 5 else ''}",
            df.index[invalid],
        )
    return ValidationResult("metric_id_format", "pass", "All metric_id values match expected format")


def check_na_consistency(df: pd.DataFrame) -> ValidationResult:
    na_cols = ["child_metric_id", "child_metric_short_name", "relationship_type",
               "relationship_category", "relationship_description"]
    available = [c for c in na_cols if c in df.columns]
    if not available:
        return ValidationResult("na_consistency", "fail", "Required columns missing")

    child_is_na = df["child_metric_id"].astype(str).str.strip().str.upper() == "NA"
    inconsistent = pd.Series(False, index=df.index)
    for col in available:
        col_is_na = df[col].astype(str).str.strip().str.upper() == "NA"
        inconsistent = inconsistent | (child_is_na != col_is_na)

    if inconsistent.any():
        return ValidationResult(
            "na_consistency", "fail",
            f"{inconsistent.sum()} rows have inconsistent NA values across relationship columns",
            df.index[inconsistent],
        )
    return ValidationResult("na_consistency", "pass", "NA values are consistent across relationship columns")


def check_relationship_type_values(df: pd.DataFrame) -> ValidationResult:
    if "relationship_type" not in df.columns:
        return ValidationResult("relationship_type_values", "fail", "relationship_type column missing")
    invalid = ~df["relationship_type"].astype(str).isin(VALID_RELATIONSHIP_TYPES)
    if invalid.any():
        bad_vals = df.loc[invalid, "relationship_type"].unique().tolist()
        return ValidationResult(
            "relationship_type_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad_vals}. Allowed: {sorted(VALID_RELATIONSHIP_TYPES)}",
            df.index[invalid],
        )
    return ValidationResult("relationship_type_values", "pass", "All relationship_type values are valid")


def check_relationship_category_values(df: pd.DataFrame) -> ValidationResult:
    if "relationship_category" not in df.columns:
        return ValidationResult("relationship_category_values", "fail", "relationship_category column missing")
    invalid = ~df["relationship_category"].astype(str).isin(VALID_RELATIONSHIP_CATEGORIES)
    if invalid.any():
        bad_vals = df.loc[invalid, "relationship_category"].unique().tolist()
        return ValidationResult(
            "relationship_category_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad_vals}. Allowed: {sorted(VALID_RELATIONSHIP_CATEGORIES)}",
            df.index[invalid],
        )
    return ValidationResult("relationship_category_values", "pass", "All relationship_category values are valid")


def check_no_trailing_columns(df: pd.DataFrame) -> ValidationResult:
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if extra:
        return ValidationResult(
            "no_trailing_columns", "fail",
            f"Unexpected extra columns found: {extra}",
        )
    return ValidationResult("no_trailing_columns", "pass", "No unexpected extra columns")


def run_all_checks(df: pd.DataFrame) -> list[ValidationResult]:
    return [
        check_expected_columns(df),
        check_column_order(df),
        check_no_trailing_columns(df),
        check_mandatory_not_null(df),
        check_no_duplicate_rows(df),
        check_metric_id_format(df),
        check_relationship_type_values(df),
        check_relationship_category_values(df),
        check_na_consistency(df),
    ]
