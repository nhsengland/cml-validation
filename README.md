# CML Proforma Validation

Validates CSV outputs of CML datasets against the CML Proforma schema Template v3.0.csv.

**Important:** These checks are to help you QA your outputs by comparing them against the rules specified in the schema and guidance. You should not consider these as comprehensive as there may be other issues in your data that they didn't detect.


## How does this differ from cml-schemas

[cml-schemas](https://github.com/nhsengland/cml-schemas) is a package that should become a dependency of your pipeline, you should use it during the creation of your outputs to ensure you have created all the required columns, and they are the relevant data types. As you will likely create one large table/dataframe which is later split into metric and dimensions, you can use cml-schemas to perform this split. So cml-schemas becomes part of your pipeline's processing.

cml-validation is more like an integration test you would run while developing your pipeline.

There is overlap between these two packages. A future development would be for cml-schemas to become a dependency of cml-validation, and you might also want to build these tests into your testing package.


## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install pandas
```

## Usage

### Auto-discover mode (default)

Run with no arguments and the tool scans the current directory for the most recent CSV per table type, identified by the timestamp after the rightmost `__` in the filename.

**Important**: Your file names must have the timestamp after `__` for auto-discover to work.

```bash
python validate.py
```

Point it at a different folder with `--folder`:

```bash
python validate.py --folder /path/to/pipeline/output
```

### Explicit mode

Pass one or more `table_type` / `csv_path` pairs directly:

```bash
python validate.py relationships relationships_2026-06-25.csv
python validate.py relationships relationships.csv metadata metadata.csv
```

### `--timestamp` flag

By default the report filename uses the current UTC time. Pass `--timestamp` to use a specific timestamp, e.g., the pipeline's own `generation_ts` so the report is directly correlated to the pipeline run:

```bash
python validate.py --timestamp "2026-06-25 22:05:01"
python validate.py --folder /output --timestamp "2026-06-25 22:05:01"
```

This produces `validation_reports/2026-06-25_22-05-01.md`.

`table_type` must be one of: `relationships`, `metadata`, `dimensions`, `metric`

## Output

Each check reports one of three statuses:

| Status | Meaning |
|---|---|
| ✅ PASS | Check passed |
| ⚠️ WARN | Technically outside the schema but expected (e.g. pipeline housekeeping columns) |
| ❌ FAIL | Genuine schema violation |

Only failures cause a non-zero exit code — warnings do not. This means the validator can be dropped into a CI pipeline and warnings won't block a build.

## Reports

Every run writes a single timestamped report to `validation_reports/`:

```
validation_reports/
    2026-06-26_09-21-27.md
    2026-06-26_09-35-14.md
    2026-06-26_10-01-00.md
    2026-06-26_10-05-00.md
```

Each file is named `YYYY-MM-DD_HH-MM-SS.md` (or matches the `--timestamp` you passed) and contains a `##` section per table plus an overall summary header. The folder is gitignored — reports live locally and are not committed.

## Checks by table

### Relationships
| Check | Description |
|---|---|
| `expected_columns` | All 7 schema columns are present |
| `column_order` | Columns appear in schema-defined order |
| `no_trailing_columns` | No unexpected extra columns |
| `mandatory_not_null` | Mandatory fields have no nulls or empty strings |
| `no_duplicate_rows` | `(metric_id, child_metric_id)` pairs are unique |
| `metric_id_format` | Suffix is one of `act/est/for/pla/var/com/inc` |
| `relationship_type_values` | Restricted to 7 allowed values |
| `relationship_category_values` | Restricted to `Direct/Indirect/NA` |
| `na_consistency` | If `child_metric_id` is `NA`, all relationship fields are too |

### Metadata
| Check | Description |
|---|---|
| `expected_columns` | All 39 schema columns are present |
| `column_order` | Columns appear in schema-defined order |
| `no_trailing_columns` | No unexpected extra columns |
| `mandatory_not_null` | Mandatory fields have no nulls or empty strings |
| `no_duplicate_metric_ids` | `metric_id` is unique |
| `metric_family_id_format` | Matches pattern: 2–4 letters followed by 4–5 digits |
| `metric_id_derived_correctly` | `metric_id` = `metric_family_id` + `_` + 3-char status suffix |
| `metric_status_values` | Restricted to 7 allowed values |
| `metric_state_values` | Restricted to 5 allowed values |
| `metric_title_length` | `metric_title` is ≤ 160 characters |
| `timestamp_format` | Date fields match expected timestamp formats |
| `metric_end_date_only_when_retired` | `metric_end_date` only populated for Deprecated/Retired metrics |
| `available_metric_category_values` | Restricted to 6 allowed values |
| `domain_values` | When populated, restricted to 6 allowed values |
| `aggregation_values` | Restricted to `Y/N` |
| `sdc_flag_values` | Restricted to `Y/N/NA` |
| `metric_owner_has_email` | `metric_owner` contains an email address |
| `sdc_description_when_flagged` | SDC description provided when flag is `Y` |

### Dimensions
| Check | Description |
|---|---|
| `fixed_columns_present` | `dimension_id`, `dimension_type_id`, `dimension_count` all exist |
| `fixed_column_order` | Fixed columns appear first, in schema order |
| `pipeline_columns` | ⚠️ `generation_ts` / `dimension_id_generation_ts` flagged if present |
| `no_accidental_foreign_columns` | No dimension column names match fields from other schema tables |
| `at_least_one_dimension_column` | At least one dimension column exists beyond the fixed columns |
| `no_duplicate_dimension_ids` | `dimension_id` is unique |
| `mandatory_not_null` | Fixed columns have no nulls |
| `dimension_count_is_integer` | `dimension_count` is numeric |
| `dimension_count_matches_type` | Count matches the number of `&`-separated parts in `dimension_type_id` |
| `dimension_type_id_columns_exist` | Every name in `dimension_type_id` has a matching column |

### Metric
| Check | Description |
|---|---|
| `expected_columns` | All 10 schema columns are present |
| `column_order` | Columns appear in schema-defined order |
| `pipeline_columns` | ⚠️ `generation_ts` / `datapoint_id_generation_ts` flagged if present |
| `mandatory_not_null` | Mandatory fields have no nulls or empty strings |
| `metric_id_format` | Suffix is one of `act/est/for/pla/var/com/inc` |
| `reporting_grain_values` | Restricted to `hourly/daily/weekly/monthly/quarterly` |
| `metric_value_numeric` | `metric_value` is an integer or float |
| `no_duplicate_datapoint_ids` | `datapoint_id` is unique |
| `duplicate_datapoint_id_diagnosis` | If duplicates exist, diagnoses whether the cause is location reference table fanout (multiple `location_type` values per `datapoint_id`) or something else |
| `datapoint_id_format` | `datapoint_id` matches its expected composite of constituent fields |
| `reporting_grain_consistent_per_metric` | Each `metric_id` uses exactly one `reporting_grain` |
| `no_future_reporting_periods` | ⚠️ Warns if any `reporting_period_start_datetime` is in the future |

## Project structure

```
validate.py                  # Entry point
validators/
    base.py                  # ValidationResult type shared across all validators
    relationships.py
    metadata.py
    dimensions.py
    metric.py
validation_reports/          # Gitignored — audit trail of all runs
```
