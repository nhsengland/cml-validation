"""Validation checks for the Dimensions table against the CML Proforma schema."""

import pandas as pd

from validators.base import ValidationResult


# Fixed columns that must always be present, in this order, at the start
FIXED_COLUMNS = ["dimension_id", "dimension_type_id", "dimension_count"]

# Pipeline housekeeping columns — valid to have, but not part of the schema.
# They exist in the ingest-area file and are dropped before production.
PIPELINE_COLUMNS = {"generation_ts", "dimension_id_generation_ts"}

# Columns from other tables that should never appear in dimensions by accident
_METRIC_COLUMNS = {
    "metric_id", "metric_family_id", "metric_status", "metric_state", "metric_title",
    "metric_start_date", "metric_end_date", "available_metric_category",
    "available_reporting_grain", "available_location_types", "available_dimension_types",
    "business_area", "business_sub_area", "domain", "numerator_source_name",
    "numerator_project_id", "numerator_source_platform", "denominator_source_name",
    "denominator_project_id", "denominator_source_platform", "metric_owner",
    "metric_short_name", "metric_alias", "metric_description", "calculation",
    "metric_purpose", "unit", "format", "target", "frequency_of_refresh",
    "aggregation", "statistical_disclosure_control_flag",
    "statistical_disclosure_control_description", "interpretation",
    "inclusion_exclusion_rules", "usage", "organisation_geog_type", "footnotes", "notes",
}
_RELATIONSHIPS_COLUMNS = {
    "child_metric_id", "child_metric_short_name", "relationship_type",
    "relationship_category", "relationship_description",
}
_SOURCE_COLUMNS = {
    "numerator_source_name", "numerator_project_id", "numerator_source_platform",
    "denominator_source_name", "denominator_project_id", "denominator_source_platform",
    "first_record_timestamp", "last_record_timestamp", "last_ingest_timestamp",
    "version_release_date", "version_release",
}
KNOWN_FOREIGN_COLUMNS = _METRIC_COLUMNS | _RELATIONSHIPS_COLUMNS | _SOURCE_COLUMNS


def _dimension_columns(df: pd.DataFrame) -> list[str]:
    """Return the variable dimension columns — everything between the fixed and pipeline columns."""
    return [c for c in df.columns if c not in FIXED_COLUMNS and c not in PIPELINE_COLUMNS]


def check_fixed_columns_present(df: pd.DataFrame) -> ValidationResult:
    missing = [c for c in FIXED_COLUMNS if c not in df.columns]
    if missing:
        return ValidationResult("fixed_columns_present", "fail", f"Required fixed columns missing: {missing}")
    return ValidationResult("fixed_columns_present", "pass", "All fixed columns present")


def check_fixed_column_order(df: pd.DataFrame) -> ValidationResult:
    """Fixed columns must appear first, in schema order."""
    leading = list(df.columns[:len(FIXED_COLUMNS)])
    if leading != FIXED_COLUMNS:
        return ValidationResult(
            "fixed_column_order", "fail",
            f"First {len(FIXED_COLUMNS)} columns should be {FIXED_COLUMNS}, got {leading}",
        )
    return ValidationResult("fixed_column_order", "pass", f"Fixed columns appear first in correct order")


def check_pipeline_columns_warning(df: pd.DataFrame) -> ValidationResult:
    """Pipeline housekeeping columns are expected in ingest files but not schema-defined."""
    present = [c for c in PIPELINE_COLUMNS if c in df.columns]
    if present:
        return ValidationResult(
            "pipeline_columns", "warn",
            f"Pipeline columns present (will be dropped before production): {sorted(present)}",
        )
    return ValidationResult("pipeline_columns", "pass", "No pipeline-only columns present")


def check_no_accidental_foreign_columns(df: pd.DataFrame) -> ValidationResult:
    """Flag any dimension columns whose names match fields from other schema tables."""
    dim_cols = _dimension_columns(df)
    accidental = [c for c in dim_cols if c in KNOWN_FOREIGN_COLUMNS]
    if accidental:
        return ValidationResult(
            "no_accidental_foreign_columns", "fail",
            f"Dimension columns match field names from other schema tables (likely copy-paste error): {accidental}",
        )
    return ValidationResult("no_accidental_foreign_columns", "pass", "No accidental foreign column names detected")


def check_at_least_one_dimension_column(df: pd.DataFrame) -> ValidationResult:
    dim_cols = _dimension_columns(df)
    if not dim_cols:
        return ValidationResult(
            "at_least_one_dimension_column", "fail",
            "No dimension columns found beyond the fixed columns",
        )
    return ValidationResult(
        "at_least_one_dimension_column", "pass",
        f"{len(dim_cols)} dimension column(s) found: {dim_cols[:5]}{'...' if len(dim_cols) > 5 else ''}",
    )


def check_no_duplicate_dimension_ids(df: pd.DataFrame) -> ValidationResult:
    if "dimension_id" not in df.columns:
        return ValidationResult("no_duplicate_dimension_ids", "fail", "dimension_id column missing")
    dupes = df.duplicated(subset=["dimension_id"], keep=False)
    if dupes.any():
        return ValidationResult(
            "no_duplicate_dimension_ids", "fail",
            f"{dupes.sum()} rows share a duplicated dimension_id",
            df.index[dupes],
        )
    return ValidationResult("no_duplicate_dimension_ids", "pass", "All dimension_id values are unique")


def check_mandatory_not_null(df: pd.DataFrame) -> ValidationResult:
    failures = {
        col: df.index[df[col].isna() | (df[col].astype(str).str.strip() == "")]
        for col in FIXED_COLUMNS
        if col in df.columns
        and (df[col].isna() | (df[col].astype(str).str.strip() == "")).any()
    }
    if failures:
        summary = {col: len(idx) for col, idx in failures.items()}
        all_failing = pd.Index(sorted({i for idx in failures.values() for i in idx}))
        return ValidationResult("mandatory_not_null", "fail", f"Null/empty in fixed columns: {summary}", all_failing)
    return ValidationResult("mandatory_not_null", "pass", "All fixed columns populated")


def check_dimension_count_matches_type(df: pd.DataFrame) -> ValidationResult:
    """dimension_count should equal the number of '&'-separated parts in dimension_type_id.
    The special value 'total' should have count 0."""
    required = {"dimension_type_id", "dimension_count"}
    if not required.issubset(df.columns):
        return ValidationResult("dimension_count_matches_type", "fail", f"Required columns missing: {required - set(df.columns)}")

    def expected_count(type_id: str) -> int:
        s = str(type_id).strip().lower()
        return 0 if s == "total" else len(s.split("&"))

    expected = df["dimension_type_id"].apply(expected_count)
    actual = pd.to_numeric(df["dimension_count"], errors="coerce")
    mismatch = actual != expected
    if mismatch.any():
        sample = df.loc[mismatch, ["dimension_type_id", "dimension_count"]].head(5).to_dict("records")
        return ValidationResult(
            "dimension_count_matches_type", "fail",
            f"{mismatch.sum()} rows have dimension_count inconsistent with dimension_type_id. Sample: {sample}",
            df.index[mismatch],
        )
    return ValidationResult("dimension_count_matches_type", "pass", "All dimension_count values consistent with dimension_type_id")


def check_dimension_type_id_columns_exist(df: pd.DataFrame) -> ValidationResult:
    """Each dimension name referenced in dimension_type_id should have a corresponding column."""
    if "dimension_type_id" not in df.columns:
        return ValidationResult("dimension_type_id_columns_exist", "fail", "dimension_type_id column missing")

    dim_cols = set(_dimension_columns(df))
    missing_cols: dict[str, list[str]] = {}

    for type_id in df["dimension_type_id"].astype(str).unique():
        if type_id.strip().lower() == "total":
            continue
        parts = [p.strip() for p in type_id.split("&")]
        absent = [p for p in parts if p and p not in dim_cols]
        if absent:
            missing_cols[type_id] = absent

    if missing_cols:
        return ValidationResult(
            "dimension_type_id_columns_exist", "fail",
            f"{len(missing_cols)} dimension_type_id value(s) reference dimension names with no matching column: {dict(list(missing_cols.items())[:3])}{'...' if len(missing_cols) > 3 else ''}",
        )
    return ValidationResult("dimension_type_id_columns_exist", "pass", "All dimension_type_id values reference existing columns")


def check_dimension_count_is_integer(df: pd.DataFrame) -> ValidationResult:
    if "dimension_count" not in df.columns:
        return ValidationResult("dimension_count_is_integer", "fail", "dimension_count column missing")
    non_int = df["dimension_count"].apply(
        lambda v: pd.isna(v) or not str(v).strip().lstrip("-").isdigit()
    )
    if non_int.any():
        bad = df.loc[non_int, "dimension_count"].unique().tolist()
        return ValidationResult(
            "dimension_count_is_integer", "fail",
            f"{non_int.sum()} non-integer dimension_count values. Got: {bad[:5]}",
            df.index[non_int],
        )
    return ValidationResult("dimension_count_is_integer", "pass", "All dimension_count values are integers")


def run_all_checks(df: pd.DataFrame) -> list[ValidationResult]:
    return [
        check_fixed_columns_present(df),
        check_fixed_column_order(df),
        check_pipeline_columns_warning(df),
        check_no_accidental_foreign_columns(df),
        check_at_least_one_dimension_column(df),
        check_no_duplicate_dimension_ids(df),
        check_mandatory_not_null(df),
        check_dimension_count_is_integer(df),
        check_dimension_count_matches_type(df),
        check_dimension_type_id_columns_exist(df),
    ]
