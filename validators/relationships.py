"""Validation checks for the Relationships table against the CML Proforma schema."""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


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
VALID_METRIC_ID_SUFFIXES = {"act", "est", "for", "pla", "var", "com", "inc"}
METRIC_ID_PATTERN = r"^[A-Za-z0-9]+_(" + "|".join(VALID_METRIC_ID_SUFFIXES) + r")$"


@dataclass
class ValidationResult:
    check_name: str
    passed: bool
    message: str
    failing_rows: Optional[pd.Index] = field(default=None)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        out = f"[{status}] {self.check_name}: {self.message}"
        if not self.passed and self.failing_rows is not None and len(self.failing_rows) > 0:
            out += f" (rows: {list(self.failing_rows[:10])}{'...' if len(self.failing_rows) > 10 else ''})"
        return out


def check_expected_columns(df: pd.DataFrame) -> ValidationResult:
    """Verify the dataframe has exactly the expected columns, no more, no less."""
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
        return ValidationResult(
            "expected_columns",
            False,
            "; ".join(parts),
        )
    return ValidationResult("expected_columns", True, "All expected columns present")


def check_column_order(df: pd.DataFrame) -> ValidationResult:
    """Verify columns appear in the schema-defined order."""
    actual = [c for c in df.columns if c in EXPECTED_COLUMNS]
    if actual != EXPECTED_COLUMNS:
        return ValidationResult(
            "column_order",
            False,
            f"Expected order {EXPECTED_COLUMNS}, got {actual}",
        )
    return ValidationResult("column_order", True, "Column order matches schema")


def check_no_duplicate_rows(df: pd.DataFrame) -> ValidationResult:
    """Each metric_id + child_metric_id pair should be unique."""
    if "metric_id" not in df.columns or "child_metric_id" not in df.columns:
        return ValidationResult("no_duplicate_rows", False, "Required columns missing, skipping")
    dupes = df.duplicated(subset=["metric_id", "child_metric_id"], keep=False)
    if dupes.any():
        return ValidationResult(
            "no_duplicate_rows",
            False,
            f"{dupes.sum()} rows are duplicated on (metric_id, child_metric_id)",
            df.index[dupes],
        )
    return ValidationResult("no_duplicate_rows", True, "No duplicate (metric_id, child_metric_id) pairs")


def check_mandatory_not_null(df: pd.DataFrame) -> ValidationResult:
    """All mandatory columns must not be null/empty."""
    available = [c for c in MANDATORY_COLUMNS if c in df.columns]
    failures = {}
    for col in available:
        null_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        if null_mask.any():
            failures[col] = df.index[null_mask]

    if failures:
        summary = {col: len(idx) for col, idx in failures.items()}
        all_failing = pd.Index(
            sorted(set(idx for idxs in failures.values() for idx in idxs))
        )
        return ValidationResult(
            "mandatory_not_null",
            False,
            f"Null/empty values in mandatory columns: {summary}",
            all_failing,
        )
    return ValidationResult("mandatory_not_null", True, "All mandatory columns populated")


def check_metric_id_format(df: pd.DataFrame) -> ValidationResult:
    """metric_id should match the expected pattern (e.g. CWT0001_act)."""
    if "metric_id" not in df.columns:
        return ValidationResult("metric_id_format", False, "metric_id column missing")
    invalid = ~df["metric_id"].astype(str).str.match(METRIC_ID_PATTERN)
    if invalid.any():
        bad_vals = df.loc[invalid, "metric_id"].unique().tolist()
        return ValidationResult(
            "metric_id_format",
            False,
            f"{invalid.sum()} metric_id values have unrecognised suffix. "
            f"Valid suffixes: {sorted(VALID_METRIC_ID_SUFFIXES)}. Got: {bad_vals[:5]}{'...' if len(bad_vals) > 5 else ''}",
            df.index[invalid],
        )
    return ValidationResult("metric_id_format", True, "All metric_id values match expected format")


def check_na_consistency(df: pd.DataFrame) -> ValidationResult:
    """When child_metric_id is NA, all relationship fields must also be NA, and vice versa."""
    na_cols = ["child_metric_id", "child_metric_short_name", "relationship_type",
               "relationship_category", "relationship_description"]
    available = [c for c in na_cols if c in df.columns]
    if not available:
        return ValidationResult("na_consistency", False, "Required columns missing")

    # Rows where child_metric_id is NA
    child_is_na = df["child_metric_id"].astype(str).str.strip().str.upper() == "NA"

    inconsistent = pd.Series(False, index=df.index)
    for col in available:
        col_is_na = df[col].astype(str).str.strip().str.upper() == "NA"
        # If child is NA, all should be NA; if child is not NA, none should be NA
        mismatch = child_is_na != col_is_na
        inconsistent = inconsistent | mismatch

    if inconsistent.any():
        return ValidationResult(
            "na_consistency",
            False,
            f"{inconsistent.sum()} rows have inconsistent NA values across relationship columns",
            df.index[inconsistent],
        )
    return ValidationResult("na_consistency", True, "NA values are consistent across relationship columns")


def check_relationship_type_values(df: pd.DataFrame) -> ValidationResult:
    """relationship_type must be one of the allowed values."""
    if "relationship_type" not in df.columns:
        return ValidationResult("relationship_type_values", False, "relationship_type column missing")
    invalid = ~df["relationship_type"].astype(str).isin(VALID_RELATIONSHIP_TYPES)
    if invalid.any():
        bad_vals = df.loc[invalid, "relationship_type"].unique().tolist()
        return ValidationResult(
            "relationship_type_values",
            False,
            f"{invalid.sum()} invalid values. Got: {bad_vals}. Allowed: {sorted(VALID_RELATIONSHIP_TYPES)}",
            df.index[invalid],
        )
    return ValidationResult("relationship_type_values", True, "All relationship_type values are valid")


def check_relationship_category_values(df: pd.DataFrame) -> ValidationResult:
    """relationship_category must be one of the allowed values."""
    if "relationship_category" not in df.columns:
        return ValidationResult("relationship_category_values", False, "relationship_category column missing")
    invalid = ~df["relationship_category"].astype(str).isin(VALID_RELATIONSHIP_CATEGORIES)
    if invalid.any():
        bad_vals = df.loc[invalid, "relationship_category"].unique().tolist()
        return ValidationResult(
            "relationship_category_values",
            False,
            f"{invalid.sum()} invalid values. Got: {bad_vals}. Allowed: {sorted(VALID_RELATIONSHIP_CATEGORIES)}",
            df.index[invalid],
        )
    return ValidationResult("relationship_category_values", True, "All relationship_category values are valid")


def check_no_trailing_columns(df: pd.DataFrame) -> ValidationResult:
    """Flag any columns beyond the expected set (e.g. stray trailing commas in CSV)."""
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if extra:
        return ValidationResult(
            "no_trailing_columns",
            False,
            f"Unexpected extra columns found: {extra}",
        )
    return ValidationResult("no_trailing_columns", True, "No unexpected extra columns")


def run_all_checks(df: pd.DataFrame) -> list[ValidationResult]:
    """Run all Relationships table checks and return a list of results."""
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
