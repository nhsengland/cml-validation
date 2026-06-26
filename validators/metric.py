"""Validation checks for the Metric table against the CML Proforma schema."""

import pandas as pd

from validators.base import ValidationResult


EXPECTED_COLUMNS = [
    "datapoint_id",
    "metric_id",
    "dimension_id",
    "reporting_grain",
    "location_id",
    "location_type",
    "reporting_period_start_datetime",
    "publication_datetime",
    "metric_value",
    "additional_metric_values",
]

MANDATORY_COLUMNS = [
    "datapoint_id",
    "metric_id",
    "reporting_grain",
    "location_id",
    "location_type",
    "reporting_period_start_datetime",
    "metric_value",
]

PIPELINE_COLUMNS = {"generation_ts", "datapoint_id_generation_ts"}

VALID_REPORTING_GRAINS = {"hourly", "daily", "weekly", "monthly", "quarterly"}

# Valid metric_status suffixes — same rule as other tables
VALID_METRIC_ID_SUFFIXES = {"act", "est", "for", "pla", "var", "com", "inc", "prov"}
METRIC_ID_PATTERN = r"^[A-Za-z0-9]+_(" + "|".join(VALID_METRIC_ID_SUFFIXES) + r")$"


def check_expected_columns(df: pd.DataFrame) -> ValidationResult:
    actual, expected = set(df.columns), set(EXPECTED_COLUMNS)
    missing = expected - actual - PIPELINE_COLUMNS
    extra = actual - expected - PIPELINE_COLUMNS
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
        first_diff = next(
            (i for i, (a, e) in enumerate(zip(actual, EXPECTED_COLUMNS)) if a != e), len(actual)
        )
        got = actual[first_diff] if first_diff < len(actual) else "missing"
        return ValidationResult(
            "column_order", "fail",
            f"First mismatch at position {first_diff}: expected '{EXPECTED_COLUMNS[first_diff]}', got '{got}'",
        )
    return ValidationResult("column_order", "pass", "Column order matches schema")


def check_pipeline_columns(df: pd.DataFrame) -> ValidationResult:
    present = sorted(c for c in PIPELINE_COLUMNS if c in df.columns)
    if present:
        return ValidationResult(
            "pipeline_columns", "warn",
            f"Pipeline columns present (will be dropped before production): {present}",
        )
    return ValidationResult("pipeline_columns", "pass", "No pipeline-only columns present")


def check_mandatory_not_null(df: pd.DataFrame) -> ValidationResult:
    failures = {
        col: df.index[df[col].isna() | (df[col].astype(str).str.strip() == "")]
        for col in MANDATORY_COLUMNS
        if col in df.columns
        and (df[col].isna() | (df[col].astype(str).str.strip() == "")).any()
    }
    if failures:
        summary = {col: len(idx) for col, idx in failures.items()}
        all_failing = pd.Index(sorted({i for idx in failures.values() for i in idx}))
        return ValidationResult("mandatory_not_null", "fail", f"Null/empty in mandatory columns: {summary}", all_failing)
    return ValidationResult("mandatory_not_null", "pass", "All mandatory columns populated")


def check_no_duplicate_datapoint_ids(df: pd.DataFrame) -> ValidationResult:
    if "datapoint_id" not in df.columns:
        return ValidationResult("no_duplicate_datapoint_ids", "fail", "datapoint_id column missing")
    dupes = df.duplicated(subset=["datapoint_id"], keep=False)
    if dupes.any():
        n_dupes = dupes.sum()
        n_distinct = df.loc[dupes, "datapoint_id"].nunique()
        return ValidationResult(
            "no_duplicate_datapoint_ids", "fail",
            f"{n_dupes} rows share a duplicated datapoint_id ({n_distinct} distinct IDs affected)",
            df.index[dupes],
        )
    return ValidationResult("no_duplicate_datapoint_ids", "pass", "All datapoint_id values are unique")


def check_duplicate_datapoint_id_diagnosis(df: pd.DataFrame) -> ValidationResult:
    """When duplicate datapoint_ids exist, diagnose whether location_type fanout is the cause.

    Groups each duplicated datapoint_id by the number of distinct location_type values.
    If any group has >1 distinct location_type, the likely cause is a one-to-many join
    on the location reference table. If all groups have exactly 1 location_type, the
    duplicates have a different root cause and the query logic needs investigation.
    """
    required = {"datapoint_id", "location_type"}
    if not required.issubset(df.columns):
        return ValidationResult("duplicate_datapoint_id_diagnosis", "fail", f"Required columns missing: {required - set(df.columns)}")

    dupes_mask = df.duplicated(subset=["datapoint_id"], keep=False)
    if not dupes_mask.any():
        return ValidationResult(
            "duplicate_datapoint_id_diagnosis", "pass",
            "No duplicates to diagnose",
        )

    duped = df.loc[dupes_mask, ["datapoint_id", "location_type"]]
    location_type_counts = (
        duped.groupby("datapoint_id")["location_type"]
        .nunique()
    )
    fanout_ids = location_type_counts[location_type_counts > 1]

    if fanout_ids.any():
        sample = fanout_ids.head(3).to_dict()
        return ValidationResult(
            "duplicate_datapoint_id_diagnosis", "fail",
            f"Likely cause: location reference table fanout. "
            f"{len(fanout_ids)} datapoint_id(s) have >1 distinct location_type. "
            f"Sample (datapoint_id → unique location_type count): {sample}",
        )
    else:
        return ValidationResult(
            "duplicate_datapoint_id_diagnosis", "fail",
            f"Duplicates present but all share the same location_type — "
            f"NOT caused by location reference fanout. Check your query logic for another source of duplication.",
        )


def check_datapoint_id_format(df: pd.DataFrame) -> ValidationResult:
    """datapoint_id must be reconstructable from its constituent parts."""
    required = {"datapoint_id", "metric_id", "reporting_grain", "location_id", "reporting_period_start_datetime"}
    if not required.issubset(df.columns):
        return ValidationResult("datapoint_id_format", "fail", f"Required columns missing: {required - set(df.columns)}")

    def build_expected(row: pd.Series) -> str:
        parts = [str(row["metric_id"])]
        if pd.notna(row.get("dimension_id")) and str(row.get("dimension_id", "")).strip():
            parts.append(str(row["dimension_id"]))
        parts += [
            str(row["reporting_grain"]),
            str(row["location_id"]),
            str(row["reporting_period_start_datetime"]),
        ]
        return "_".join(parts)

    # Only check rows where all constituent parts are non-null — null parts are
    # already caught by check_mandatory_not_null and would produce misleading noise here.
    complete = df[list(required)].notna().all(axis=1)
    expected = df.apply(build_expected, axis=1)
    mismatch = complete & (df["datapoint_id"].astype(str) != expected)
    if mismatch.any():
        sample = df.loc[mismatch, ["datapoint_id"]].assign(expected=expected[mismatch]).head(3).to_dict("records")
        return ValidationResult(
            "datapoint_id_format", "fail",
            f"{mismatch.sum()} datapoint_id values don't match the expected composite. Sample: {sample}",
            df.index[mismatch],
        )
    return ValidationResult("datapoint_id_format", "pass", "All datapoint_id values match expected composite format")


def check_metric_id_format(df: pd.DataFrame) -> ValidationResult:
    if "metric_id" not in df.columns:
        return ValidationResult("metric_id_format", "fail", "metric_id column missing")
    invalid = ~df["metric_id"].astype(str).str.match(METRIC_ID_PATTERN)
    if invalid.any():
        bad = df.loc[invalid, "metric_id"].unique().tolist()
        return ValidationResult(
            "metric_id_format", "fail",
            f"{invalid.sum()} metric_id values have unrecognised suffix. "
            f"Valid suffixes: {sorted(VALID_METRIC_ID_SUFFIXES)}. Got: {bad[:5]}{'...' if len(bad) > 5 else ''}",
            df.index[invalid],
        )
    return ValidationResult("metric_id_format", "pass", "All metric_id values match expected format")


def check_reporting_grain_values(df: pd.DataFrame) -> ValidationResult:
    if "reporting_grain" not in df.columns:
        return ValidationResult("reporting_grain_values", "fail", "reporting_grain column missing")
    invalid = ~df["reporting_grain"].astype(str).str.lower().isin(VALID_REPORTING_GRAINS)
    if invalid.any():
        bad = df.loc[invalid, "reporting_grain"].unique().tolist()
        return ValidationResult(
            "reporting_grain_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_REPORTING_GRAINS)}",
            df.index[invalid],
        )
    return ValidationResult("reporting_grain_values", "pass", "All reporting_grain values are valid")


def check_metric_value_numeric(df: pd.DataFrame) -> ValidationResult:
    if "metric_value" not in df.columns:
        return ValidationResult("metric_value_numeric", "fail", "metric_value column missing")
    populated = df["metric_value"].notna() & (df["metric_value"].astype(str).str.strip() != "")
    coerced = pd.to_numeric(df.loc[populated, "metric_value"], errors="coerce")
    non_numeric = populated & coerced.isna().reindex(df.index, fill_value=False)
    if non_numeric.any():
        bad = df.loc[non_numeric, "metric_value"].unique().tolist()
        return ValidationResult(
            "metric_value_numeric", "fail",
            f"{non_numeric.sum()} metric_value entries are not numeric. Got: {bad[:5]}{'...' if len(bad) > 5 else ''}",
            df.index[non_numeric],
        )
    return ValidationResult("metric_value_numeric", "pass", "All metric_value entries are numeric")


def check_reporting_grain_consistent_per_metric(df: pd.DataFrame) -> ValidationResult:
    """Each metric_id must use exactly one reporting_grain across all its rows."""
    required = {"metric_id", "reporting_grain"}
    if not required.issubset(df.columns):
        return ValidationResult("reporting_grain_consistent_per_metric", "fail", f"Required columns missing: {required - set(df.columns)}")

    grain_counts = df.groupby("metric_id")["reporting_grain"].nunique()
    inconsistent = grain_counts[grain_counts > 1]
    if not inconsistent.empty:
        sample = inconsistent.head(5).to_dict()
        return ValidationResult(
            "reporting_grain_consistent_per_metric", "fail",
            f"{len(inconsistent)} metric_id(s) have more than one reporting_grain. Sample: {sample}",
        )
    return ValidationResult("reporting_grain_consistent_per_metric", "pass", "Each metric_id uses a consistent reporting_grain")


def check_no_future_reporting_periods(df: pd.DataFrame) -> ValidationResult:
    """reporting_period_start_datetime should not be in the future."""
    if "reporting_period_start_datetime" not in df.columns:
        return ValidationResult("no_future_reporting_periods", "fail", "reporting_period_start_datetime column missing")
    parsed = pd.to_datetime(df["reporting_period_start_datetime"], errors="coerce")
    today = pd.Timestamp.now().normalize()
    future = parsed.notna() & (parsed > today)
    if future.any():
        return ValidationResult(
            "no_future_reporting_periods", "warn",
            f"{future.sum()} rows have a reporting_period_start_datetime in the future",
            df.index[future],
        )
    return ValidationResult("no_future_reporting_periods", "pass", "No future reporting periods found")


def run_all_checks(df: pd.DataFrame) -> list[ValidationResult]:
    return [
        check_expected_columns(df),
        check_column_order(df),
        check_pipeline_columns(df),
        check_mandatory_not_null(df),
        check_metric_id_format(df),
        check_reporting_grain_values(df),
        check_metric_value_numeric(df),
        check_no_duplicate_datapoint_ids(df),
        check_duplicate_datapoint_id_diagnosis(df),
        check_datapoint_id_format(df),
        check_reporting_grain_consistent_per_metric(df),
        check_no_future_reporting_periods(df),
    ]
