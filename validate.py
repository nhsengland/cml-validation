"""Entry point for CML Proforma schema validation.

Usage:
    python validate.py <table_type> <csv_path>

    table_type: relationships (more to follow)
    csv_path:   path to the CSV file to validate

Example:
    python validate.py relationships relationships_2026-06-25.csv
"""

import sys
import pandas as pd
from validators import relationships


TABLE_VALIDATORS = {
    "relationships": relationships.run_all_checks,
}


def load_csv(path: str) -> pd.DataFrame:
    try:
        # keep_default_na=False prevents pandas from silently converting the
        # literal string "NA" (a valid schema sentinel) into NaN.
        # na_values=[''] ensures truly empty cells are still treated as null.
        df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        print(f"Error: file not found: {path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
    # Strip whitespace from column names to guard against stray spaces
    df.columns = [c.strip() for c in df.columns]
    # Drop fully-empty columns (e.g. trailing comma in CSV)
    df = df.loc[:, ~df.columns.str.fullmatch(r"Unnamed.*")]
    return df


def run(table_type: str, csv_path: str) -> None:
    if table_type not in TABLE_VALIDATORS:
        supported = ", ".join(sorted(TABLE_VALIDATORS))
        print(f"Unknown table type '{table_type}'. Supported: {supported}")
        sys.exit(1)

    print(f"Loading {csv_path} ...")
    df = load_csv(csv_path)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns.\n")

    validator = TABLE_VALIDATORS[table_type]
    results = validator(df)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    for result in results:
        print(result)

    print(f"\n--- {passed}/{len(results)} checks passed ---")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    run(table_type=sys.argv[1].lower(), csv_path=sys.argv[2])
