"""CML Proforma schema validation.

Two modes:

  Auto-discover (default)
    Scans a folder for the most recent CSV per table type, identified by the
    timestamp embedded after the rightmost '__' in the filename.

        python validate.py
        python validate.py --folder /path/to/pipeline/output

  Explicit pairs
    Pass one or more table_type / csv_path pairs directly.

        python validate.py relationships relationships.csv
        python validate.py relationships relationships.csv metadata metadata.csv

  Both modes accept an optional --timestamp flag. Pass the pipeline's own
  generation_ts to make the report filename match the pipeline run exactly.
  Without it, the current UTC time is used.

        python validate.py --timestamp "2026-06-25 22:05:01"
        python validate.py --folder /output --timestamp "2026-06-25 22:05:01"

Table types: relationships, metadata, dimensions, metric
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd

from validators import relationships, metadata, dimensions, metric

REPORT_DIR = "validation_reports"

TABLE_VALIDATORS = {
    "relationships": relationships.run_all_checks,
    "metadata": metadata.run_all_checks,
    "dimensions": dimensions.run_all_checks,
    "metric": metric.run_all_checks,
}

# Order in which tables appear in the report when auto-discovered
TABLE_ORDER = ["relationships", "metadata", "dimensions", "metric"]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _matches_table(filename: str, table_type: str) -> bool:
    """Return True if filename looks like it belongs to the given table type."""
    name = filename.lower()
    if table_type == "metric":
        # 'metadata' also contains 'metric' as a substring — exclude it
        return "metric" in name and "metadata" not in name
    return table_type in name


def _extract_file_timestamp(filepath: str) -> datetime | None:
    """Parse the timestamp embedded after the rightmost '__' in a filename.

    Expects a segment like '2026-06-25--22-05-01' or '2026-06-25 22:05:01'.
    Falls back to file mtime so every file gets a sort key.
    """
    stem = os.path.basename(filepath)
    # Strip all extensions (handles .csv.csv)
    while True:
        root, ext = os.path.splitext(stem)
        if ext.lower() == ".csv":
            stem = root
        else:
            break

    if "__" in stem:
        raw = stem.rsplit("__", 1)[-1]
        for fmt in ("%Y-%m-%d--%H-%M-%S", "%Y-%m-%d_%H-%M-%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

    # Fall back to file modification time
    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath))
    except OSError:
        return datetime.min


def find_latest_file(folder: str, table_type: str) -> str | None:
    """Return the path to the most recent CSV for table_type in folder, or None."""
    try:
        candidates = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".csv") and _matches_table(f, table_type)
        ]
    except FileNotFoundError:
        print(f"Error: folder not found: {folder}")
        sys.exit(1)

    if not candidates:
        return None

    return max(candidates, key=_extract_file_timestamp)


def discover_pairs(folder: str) -> list[tuple[str, str]]:
    """Auto-discover the latest file for each table type in folder."""
    pairs = []
    for table_type in TABLE_ORDER:
        path = find_latest_file(folder, table_type)
        if path:
            pairs.append((table_type, path))
        else:
            print(f"[{table_type}] No matching file found in '{folder}' — skipping.")
    return pairs


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _section_lines(table_type: str, csv_path: str, df: pd.DataFrame, results: list) -> list[str]:
    total = len(results)
    n_pass = sum(1 for r in results if r.level == "pass")
    n_warn = sum(1 for r in results if r.level == "warn")
    n_fail = sum(1 for r in results if r.level == "fail")

    summary_parts = [f"**{n_pass}/{total} passed**"]
    if n_warn:
        summary_parts.append(f"⚠️ {n_warn} warning{'s' if n_warn > 1 else ''}")
    if n_fail:
        summary_parts.append(f"❌ {n_fail} failure{'s' if n_fail > 1 else ''}")

    lines = [
        f"## {table_type.capitalize()} — `{os.path.basename(csv_path)}`",
        "",
        f"Rows: {len(df)} &nbsp; Columns: {len(df.columns)} &nbsp; Result: {', '.join(summary_parts)}",
        "",
        "| Check | Status | Details |",
        "|---|:---:|---|",
    ]
    for r in results:
        icon = {"pass": "✅ PASS", "warn": "⚠️ WARN", "fail": "❌ FAIL"}[r.level]
        detail = r.message.replace("|", "\\|")
        lines.append(f"| `{r.check_name}` | {icon} | {detail} |")

    lines += [""]
    return lines


def _ts_for_filename(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d_%H-%M-%S")


def _ts_for_display(ts: datetime, is_pipeline: bool) -> str:
    label = "pipeline run" if is_pipeline else "UTC"
    return ts.strftime("%Y-%m-%d %H:%M:%S") + f" ({label})"


# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------

def validate_table(table_type: str, csv_path: str) -> tuple:
    if table_type not in TABLE_VALIDATORS:
        supported = ", ".join(sorted(TABLE_VALIDATORS))
        print(f"Unknown table type '{table_type}'. Supported: {supported}")
        sys.exit(1)

    print(f"[{table_type}] Loading {csv_path} ...")
    df = load_csv(csv_path)
    print(f"[{table_type}] Loaded {len(df)} rows, {len(df.columns)} columns.\n")

    results = TABLE_VALIDATORS[table_type](df)

    n_pass = sum(1 for r in results if r.level == "pass")
    n_warn = sum(1 for r in results if r.level == "warn")
    n_fail = sum(1 for r in results if r.level == "fail")

    for result in results:
        print(result)

    summary = f"--- {n_pass}/{len(results)} passed"
    if n_warn:
        summary += f", {n_warn} warning{'s' if n_warn > 1 else ''}"
    if n_fail:
        summary += f", {n_fail} failure{'s' if n_fail > 1 else ''}"
    print(f"\n{summary} ---\n")

    return df, results


def run(pairs: list[tuple[str, str]], report_ts: datetime, is_pipeline_ts: bool) -> None:
    all_results = []
    per_table = []

    for table_type, csv_path in pairs:
        df, results = validate_table(table_type, csv_path)
        all_results.extend(results)
        per_table.append((df, results))

    total_pass = sum(1 for r in all_results if r.level == "pass")
    total_warn = sum(1 for r in all_results if r.level == "warn")
    total_fail = sum(1 for r in all_results if r.level == "fail")
    total = len(all_results)

    overall_parts = [f"**{total_pass}/{total} passed**"]
    if total_warn:
        overall_parts.append(f"⚠️ {total_warn} warning{'s' if total_warn > 1 else ''}")
    if total_fail:
        overall_parts.append(f"❌ {total_fail} failure{'s' if total_fail > 1 else ''}")

    display_ts = _ts_for_display(report_ts, is_pipeline_ts)
    lines = [
        f"# CML Validation — {display_ts}",
        "",
        f"Tables validated: {', '.join(f'`{t}`' for t, _ in pairs)} &nbsp; Overall: {', '.join(overall_parts)}",
        "",
        "---",
        "",
    ]
    for (table_type, csv_path), (df, results) in zip(pairs, per_table):
        lines += _section_lines(table_type, csv_path, df, results)
        lines += ["---", ""]

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, f"{_ts_for_filename(report_ts)}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Report written to {report_path}")

    if total_fail:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_timestamp(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d_%H-%M-%S", "%Y-%m-%d--%H-%M-%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    print(f"Error: could not parse --timestamp '{raw}'. Expected format: 'YYYY-MM-DD HH:MM:SS'")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate CML datasets against the Proforma schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pairs",
        nargs="*",
        metavar="TABLE_TYPE CSV_PATH",
        help="Explicit table_type / csv_path pairs (must be even number of args).",
    )
    parser.add_argument(
        "--folder", "-f",
        default=".",
        metavar="PATH",
        help="Folder to scan for the latest CSV per table type (default: current directory).",
    )
    parser.add_argument(
        "--timestamp", "-t",
        metavar="TS",
        help="Timestamp to use in the report filename, e.g. '2026-06-25 22:05:01'. "
             "Pass the pipeline's generation_ts to link the report to the pipeline run. "
             "Defaults to current UTC time.",
    )

    args = parser.parse_args()

    if args.pairs and len(args.pairs) % 2 != 0:
        parser.error("Pairs must be even: each table_type needs a csv_path.")

    if args.timestamp:
        report_ts = parse_timestamp(args.timestamp)
        is_pipeline_ts = True
    else:
        report_ts = datetime.now(timezone.utc).replace(tzinfo=None)
        is_pipeline_ts = False

    if args.pairs:
        pairs = [(args.pairs[i].lower(), args.pairs[i + 1]) for i in range(0, len(args.pairs), 2)]
    else:
        print(f"Auto-discovering latest files in '{args.folder}' ...\n")
        pairs = discover_pairs(args.folder)
        if not pairs:
            print("No matching files found. Exiting.")
            sys.exit(1)

    run(pairs, report_ts, is_pipeline_ts)


if __name__ == "__main__":
    main()
