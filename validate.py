"""Entry point for CML Proforma schema validation.

Usage:
    python validate.py <table_type> <csv_path>

    table_type: relationships (more to follow)
    csv_path:   path to the CSV file to validate

Example:
    python validate.py relationships relationships_2026-06-25.csv
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd

from validators import relationships, metadata

REPORT_DIR = "validation_reports"
REPORT_FILE = os.path.join(REPORT_DIR, "validation_report.md")

TABLE_VALIDATORS = {
    "relationships": relationships.run_all_checks,
    "metadata": metadata.run_all_checks,
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
    df.columns = [c.strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.fullmatch(r"Unnamed.*")]
    return df


def append_report(table_type: str, csv_path: str, df: pd.DataFrame, results: list) -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"## {table_type.capitalize()} — `{os.path.basename(csv_path)}` — {timestamp}",
        "",
        f"Rows: {len(df)} &nbsp; Columns: {len(df.columns)} &nbsp; Result: **{passed}/{total} checks passed**",
        "",
        "| Check | Status | Details |",
        "|---|:---:|---|",
    ]
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        detail = r.message.replace("|", "\\|")
        lines.append(f"| `{r.check_name}` | {status} | {detail} |")

    lines += ["", "---", ""]

    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nReport appended to {REPORT_FILE}")


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

    append_report(table_type, csv_path, df, results)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    run(table_type=sys.argv[1].lower(), csv_path=sys.argv[2])
