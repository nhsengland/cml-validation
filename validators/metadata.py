"""Validation checks for the Metadata table against the CML Proforma schema."""

import re
import pandas as pd

from validators.base import ValidationResult


EXPECTED_COLUMNS = [
    "metric_family_id",
    "metric_id",
    "metric_status",
    "metric_state",
    "metric_title",
    "metric_start_date",
    "metric_end_date",
    "available_metric_category",
    "available_reporting_grain",
    "available_location_types",
    "available_dimension_types",
    "business_area",
    "business_sub_area",
    "domain",
    "numerator_source_name",
    "numerator_project_id",
    "numerator_source_platform",
    "denominator_source_name",
    "denominator_project_id",
    "denominator_source_platform",
    "metric_owner",
    "metric_short_name",
    "metric_alias",
    "metric_description",
    "calculation",
    "metric_purpose",
    "unit",
    "format",
    "target",
    "frequency_of_refresh",
    "aggregation",
    "statistical_disclosure_control_flag",
    "statistical_disclosure_control_description",
    "interpretation",
    "inclusion_exclusion_rules",
    "usage",
    "organisation_geog_type",
    "footnotes",
    "notes",
]

MANDATORY_COLUMNS = [
    "metric_family_id",
    "metric_id",
    "metric_status",
    "metric_state",
    "metric_title",
    "metric_start_date",
    "available_metric_category",
    "available_reporting_grain",
    "available_location_types",
    "business_area",
    "business_sub_area",
    "numerator_source_name",
    "denominator_source_name",
    "metric_owner",
    "metric_description",
    "metric_purpose",
    "unit",
    "format",
    "frequency_of_refresh",
    "aggregation",
    "statistical_disclosure_control_flag",
]

VALID_METRIC_STATUSES = {
    "Actual", "Estimate", "Forecast", "Planned", "Variance", "Complete", "Incomplete",
    "Provisional",
}

METRIC_STATUS_SUFFIX_MAP = {
    "Actual": "act",
    "Estimate": "est",
    "Forecast": "for",
    "Planned": "pla",
    "Variance": "var",
    "Complete": "com",
    "Incomplete": "inc",
    "Provisional": "prov",
}

VALID_METRIC_STATES = {
    "Completed - Live",
    "Completed - Not Live",
    "In development - Not Live",
    "Deprecated",
    "Retired",
}

VALID_METRIC_CATEGORIES = {
    "Pre-release production",
    "Pre-release 24hr",
    "Official stats published",
    "Official stats in development published",
    "MI internal",
    "MI published",
}

VALID_DOMAINS = {"Finance", "Access", "Context", "Quality of care", "Activity", "Other"}

VALID_AGGREGATION = {"Y", "N"}

VALID_SDC_FLAGS = {"Y", "N", "NA"}

# 2-4 letters followed by 4-5 digits
METRIC_FAMILY_ID_PATTERN = r"^[A-Za-z]{2,4}[0-9]{4,5}$"

# Accepts ISO (YYYY-MM-DD) and UK (DD/MM/YYYY) date prefixes, T or space separator, optional fractional seconds and Z
TIMESTAMP_PATTERNS = [
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?[zZ]?)?$",
    r"^\d{2}/\d{2}/\d{4}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?[zZ]?)?$",
]


def _is_valid_timestamp(val: str) -> bool:
    return any(re.match(p, str(val).strip()) for p in TIMESTAMP_PATTERNS)


def check_expected_columns(df: pd.DataFrame) -> ValidationResult:
    actual, expected = set(df.columns), set(EXPECTED_COLUMNS)
    missing, extra = expected - actual, actual - expected
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
        return ValidationResult(
            "column_order", "fail",
            f"First mismatch at position {first_diff}: expected '{EXPECTED_COLUMNS[first_diff]}', "
            f"got '{actual[first_diff] if first_diff < len(actual) else 'missing'}'",
        )
    return ValidationResult("column_order", "pass", "Column order matches schema")


def check_no_trailing_columns(df: pd.DataFrame) -> ValidationResult:
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if extra:
        return ValidationResult("no_trailing_columns", "fail", f"Unexpected extra columns: {extra}")
    return ValidationResult("no_trailing_columns", "pass", "No unexpected extra columns")


def check_no_duplicate_metric_ids(df: pd.DataFrame) -> ValidationResult:
    if "metric_id" not in df.columns:
        return ValidationResult("no_duplicate_metric_ids", "fail", "metric_id column missing")
    dupes = df.duplicated(subset=["metric_id"], keep=False)
    if dupes.any():
        return ValidationResult(
            "no_duplicate_metric_ids", "fail",
            f"{dupes.sum()} rows share a duplicated metric_id",
            df.index[dupes],
        )
    return ValidationResult("no_duplicate_metric_ids", "pass", "All metric_id values are unique")


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
        return ValidationResult("mandatory_not_null", "fail", f"Null/empty in mandatory columns: {summary}", all_failing)
    return ValidationResult("mandatory_not_null", "pass", "All mandatory columns populated")


def check_metric_family_id_format(df: pd.DataFrame) -> ValidationResult:
    if "metric_family_id" not in df.columns:
        return ValidationResult("metric_family_id_format", "fail", "metric_family_id column missing")
    invalid = ~df["metric_family_id"].astype(str).str.match(METRIC_FAMILY_ID_PATTERN)
    if invalid.any():
        bad = df.loc[invalid, "metric_family_id"].unique().tolist()
        return ValidationResult(
            "metric_family_id_format", "fail",
            f"{invalid.sum()} values don't match pattern (2-4 letters + 4-5 digits). Got: {bad[:5]}{'...' if len(bad) > 5 else ''}",
            df.index[invalid],
        )
    return ValidationResult("metric_family_id_format", "pass", "All metric_family_id values match expected format")


def check_metric_id_derived_correctly(df: pd.DataFrame) -> ValidationResult:
    required = {"metric_id", "metric_family_id", "metric_status"}
    if not required.issubset(df.columns):
        return ValidationResult("metric_id_derived_correctly", "fail", f"Required columns missing: {required - set(df.columns)}")

    known_status = df["metric_status"].isin(METRIC_STATUS_SUFFIX_MAP)
    expected_ids = (
        df["metric_family_id"].astype(str)
        + "_"
        + df["metric_status"].map(METRIC_STATUS_SUFFIX_MAP).fillna("")
    )
    mismatch = known_status & (df["metric_id"].astype(str) != expected_ids)
    if mismatch.any():
        sample = df.loc[mismatch, ["metric_id", "metric_family_id", "metric_status"]].head(5).to_dict("records")
        return ValidationResult(
            "metric_id_derived_correctly", "fail",
            f"{mismatch.sum()} metric_id values don't match expected derivation. Sample: {sample}",
            df.index[mismatch],
        )
    return ValidationResult("metric_id_derived_correctly", "pass", "All metric_id values correctly derived from metric_family_id and metric_status")


def check_metric_status_values(df: pd.DataFrame) -> ValidationResult:
    if "metric_status" not in df.columns:
        return ValidationResult("metric_status_values", "fail", "metric_status column missing")
    invalid = ~df["metric_status"].astype(str).isin(VALID_METRIC_STATUSES)
    if invalid.any():
        bad = df.loc[invalid, "metric_status"].unique().tolist()
        return ValidationResult(
            "metric_status_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_METRIC_STATUSES)}",
            df.index[invalid],
        )
    return ValidationResult("metric_status_values", "pass", "All metric_status values are valid")


def check_metric_state_values(df: pd.DataFrame) -> ValidationResult:
    if "metric_state" not in df.columns:
        return ValidationResult("metric_state_values", "fail", "metric_state column missing")
    invalid = ~df["metric_state"].astype(str).isin(VALID_METRIC_STATES)
    if invalid.any():
        bad = df.loc[invalid, "metric_state"].unique().tolist()
        return ValidationResult(
            "metric_state_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_METRIC_STATES)}",
            df.index[invalid],
        )
    return ValidationResult("metric_state_values", "pass", "All metric_state values are valid")


def check_metric_title_length(df: pd.DataFrame) -> ValidationResult:
    if "metric_title" not in df.columns:
        return ValidationResult("metric_title_length", "fail", "metric_title column missing")
    too_long = df["metric_title"].astype(str).str.len() > 160
    if too_long.any():
        return ValidationResult(
            "metric_title_length", "fail",
            f"{too_long.sum()} metric_title values exceed 160 characters",
            df.index[too_long],
        )
    return ValidationResult("metric_title_length", "pass", "All metric_title values are within 160 characters")


def check_timestamp_columns(df: pd.DataFrame) -> ValidationResult:
    results = {}
    for col in ["metric_start_date", "metric_end_date"]:
        if col not in df.columns:
            continue
        populated = df[col].notna() & (df[col].astype(str).str.strip() != "")
        if not populated.any():
            continue
        invalid = populated & ~df[col].astype(str).apply(_is_valid_timestamp)
        if invalid.any():
            results[col] = df.index[invalid]

    if results:
        summary = {col: len(idx) for col, idx in results.items()}
        all_failing = pd.Index(sorted({i for idx in results.values() for i in idx}))
        return ValidationResult(
            "timestamp_format", "fail",
            f"Invalid timestamp format in: {summary}. Expected YYYY-MM-DDTHH:MM:SS.sssZ or DD/MM/YYYYTHH:MM:SS.sssz",
            all_failing,
        )
    return ValidationResult("timestamp_format", "pass", "All timestamp values are valid")


def check_metric_end_date_only_when_retired(df: pd.DataFrame) -> ValidationResult:
    required = {"metric_end_date", "metric_state"}
    if not required.issubset(df.columns):
        return ValidationResult("metric_end_date_only_when_retired", "fail", f"Required columns missing: {required - set(df.columns)}")

    end_date_populated = df["metric_end_date"].notna() & (df["metric_end_date"].astype(str).str.strip() != "")
    still_active = ~df["metric_state"].isin({"Deprecated", "Retired"})
    violation = end_date_populated & still_active
    if violation.any():
        return ValidationResult(
            "metric_end_date_only_when_retired", "fail",
            f"{violation.sum()} rows have metric_end_date populated but metric_state is not Deprecated or Retired",
            df.index[violation],
        )
    return ValidationResult("metric_end_date_only_when_retired", "pass", "metric_end_date only populated for Deprecated/Retired metrics")


def check_available_metric_category_values(df: pd.DataFrame) -> ValidationResult:
    if "available_metric_category" not in df.columns:
        return ValidationResult("available_metric_category_values", "fail", "available_metric_category column missing")
    invalid = ~df["available_metric_category"].astype(str).isin(VALID_METRIC_CATEGORIES)
    if invalid.any():
        bad = df.loc[invalid, "available_metric_category"].unique().tolist()
        return ValidationResult(
            "available_metric_category_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_METRIC_CATEGORIES)}",
            df.index[invalid],
        )
    return ValidationResult("available_metric_category_values", "pass", "All available_metric_category values are valid")


def check_domain_values(df: pd.DataFrame) -> ValidationResult:
    if "domain" not in df.columns:
        return ValidationResult("domain_values", "fail", "domain column missing")
    populated = df["domain"].notna() & (df["domain"].astype(str).str.strip() != "")
    invalid = populated & ~df["domain"].astype(str).isin(VALID_DOMAINS)
    if invalid.any():
        bad = df.loc[invalid, "domain"].unique().tolist()
        return ValidationResult(
            "domain_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_DOMAINS)}",
            df.index[invalid],
        )
    return ValidationResult("domain_values", "pass", "All domain values are valid")


def check_aggregation_values(df: pd.DataFrame) -> ValidationResult:
    if "aggregation" not in df.columns:
        return ValidationResult("aggregation_values", "fail", "aggregation column missing")
    invalid = ~df["aggregation"].astype(str).isin(VALID_AGGREGATION)
    if invalid.any():
        bad = df.loc[invalid, "aggregation"].unique().tolist()
        return ValidationResult(
            "aggregation_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_AGGREGATION)}",
            df.index[invalid],
        )
    return ValidationResult("aggregation_values", "pass", "All aggregation values are valid")


def check_sdc_flag_values(df: pd.DataFrame) -> ValidationResult:
    if "statistical_disclosure_control_flag" not in df.columns:
        return ValidationResult("sdc_flag_values", "fail", "statistical_disclosure_control_flag column missing")
    invalid = ~df["statistical_disclosure_control_flag"].astype(str).isin(VALID_SDC_FLAGS)
    if invalid.any():
        bad = df.loc[invalid, "statistical_disclosure_control_flag"].unique().tolist()
        return ValidationResult(
            "sdc_flag_values", "fail",
            f"{invalid.sum()} invalid values. Got: {bad}. Allowed: {sorted(VALID_SDC_FLAGS)}",
            df.index[invalid],
        )
    return ValidationResult("sdc_flag_values", "pass", "All statistical_disclosure_control_flag values are valid")


def check_metric_owner_has_email(df: pd.DataFrame) -> ValidationResult:
    if "metric_owner" not in df.columns:
        return ValidationResult("metric_owner_has_email", "fail", "metric_owner column missing")
    populated = df["metric_owner"].notna() & (df["metric_owner"].astype(str).str.strip() != "")
    has_email = df["metric_owner"].astype(str).str.contains(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", regex=True)
    missing_email = populated & ~has_email
    if missing_email.any():
        return ValidationResult(
            "metric_owner_has_email", "fail",
            f"{missing_email.sum()} metric_owner values don't contain an email address",
            df.index[missing_email],
        )
    return ValidationResult("metric_owner_has_email", "pass", "All metric_owner values contain an email address")


def check_sdc_description_when_flagged(df: pd.DataFrame) -> ValidationResult:
    required = {"statistical_disclosure_control_flag", "statistical_disclosure_control_description"}
    if not required.issubset(df.columns):
        return ValidationResult("sdc_description_when_flagged", "fail", f"Required columns missing: {required - set(df.columns)}")

    flagged = df["statistical_disclosure_control_flag"].astype(str) == "Y"
    no_description = df["statistical_disclosure_control_description"].isna() | (
        df["statistical_disclosure_control_description"].astype(str).str.strip() == ""
    )
    violation = flagged & no_description
    if violation.any():
        return ValidationResult(
            "sdc_description_when_flagged", "fail",
            f"{violation.sum()} rows have SDC flag = Y but no description provided",
            df.index[violation],
        )
    return ValidationResult("sdc_description_when_flagged", "pass", "All SDC-flagged rows have a description")


def run_all_checks(df: pd.DataFrame) -> list[ValidationResult]:
    return [
        check_expected_columns(df),
        check_column_order(df),
        check_no_trailing_columns(df),
        check_mandatory_not_null(df),
        check_no_duplicate_metric_ids(df),
        check_metric_family_id_format(df),
        check_metric_id_derived_correctly(df),
        check_metric_status_values(df),
        check_metric_state_values(df),
        check_metric_title_length(df),
        check_timestamp_columns(df),
        check_metric_end_date_only_when_retired(df),
        check_available_metric_category_values(df),
        check_domain_values(df),
        check_aggregation_values(df),
        check_sdc_flag_values(df),
        check_metric_owner_has_email(df),
        check_sdc_description_when_flagged(df),
    ]
