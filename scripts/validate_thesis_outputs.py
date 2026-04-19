"""Sanity-check for chapter-5 thesis output artifacts.

Checks:
- required files exist in summary directory
- P4 has uniform replication counts by algorithm
- D2..D5 by-algorithm table has expected n per algorithm
- Markdown contains sections A/B/C/D and N_min line
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED_FILES = [
    "p4_growth20.jsonl",
    "final_table_for_thesis.md",
    "final_table_p1_p4.csv",
    "final_table_d2_d5_pooled.csv",
    "final_table_d2_d5_by_algo.csv",
]

EXPECTED_ALGOS = {"FIFO", "PQ", "AGING", "EDF", "HYBRID"}


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _check_p4(summary_dir: Path, expected_n: int) -> list[str]:
    errors: list[str] = []
    rows = _load_jsonl(summary_dir / "p4_growth20.jsonl")
    by_algo = Counter(r.get("algorithm") for r in rows)

    missing_algos = EXPECTED_ALGOS - set(by_algo)
    extra_algos = set(by_algo) - EXPECTED_ALGOS
    if missing_algos:
        errors.append(f"P4 missing algorithms: {sorted(missing_algos)}")
    if extra_algos:
        errors.append(f"P4 unexpected algorithms: {sorted(extra_algos)}")

    for algo in sorted(EXPECTED_ALGOS):
        count = by_algo.get(algo, 0)
        if count != expected_n:
            errors.append(f"P4 count mismatch for {algo}: got {count}, expected {expected_n}")

    return errors


def _check_d_by_algo(summary_dir: Path, expected_n: int) -> list[str]:
    errors: list[str] = []
    path = summary_dir / "final_table_d2_d5_by_algo.csv"
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    grouped: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        staffing = row.get("staffing_N", "")
        algorithm = row.get("algorithm", "")
        n_val = int(float(row.get("n", "0")))
        grouped[staffing][algorithm] = n_val

    for staffing in ("2", "3", "4", "5", "2.0", "3.0", "4.0", "5.0", "2.000000", "3.000000", "4.000000", "5.000000"):
        if staffing in grouped:
            by_algo = grouped[staffing]
            break
    # Validate all groups regardless of formatting style.
    for staffing, by_algo in grouped.items():
        missing_algos = EXPECTED_ALGOS - set(by_algo)
        extra_algos = set(by_algo) - EXPECTED_ALGOS
        if missing_algos:
            errors.append(f"D-table staffing {staffing} missing algorithms: {sorted(missing_algos)}")
        if extra_algos:
            errors.append(f"D-table staffing {staffing} unexpected algorithms: {sorted(extra_algos)}")
        for algo in sorted(EXPECTED_ALGOS):
            count = by_algo.get(algo, 0)
            if count != expected_n:
                errors.append(
                    f"D-table n mismatch staffing {staffing}, algo {algo}: "
                    f"got {count}, expected {expected_n}"
                )

    return errors


def _check_markdown(summary_dir: Path) -> list[str]:
    errors: list[str] = []
    text = (summary_dir / "final_table_for_thesis.md").read_text(encoding="utf-8")
    required_tokens = [
        "## Section A:",
        "## Section B:",
        "## Section C:",
        "## Section D:",
        "N_min:",
    ]
    for token in required_tokens:
        if token not in text:
            errors.append(f"Markdown missing token: {token}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate chapter-5 thesis output artifacts")
    parser.add_argument(
        "--summary-dir",
        default="results/ch5/final_series/summary",
        help="Path to summary directory",
    )
    parser.add_argument(
        "--expected-p4-runs",
        type=int,
        default=30,
        help="Expected replications per algorithm for P4",
    )
    parser.add_argument(
        "--expected-d-runs",
        type=int,
        default=20,
        help="Expected replications per algorithm in D2-D5 by-algo table",
    )
    args = parser.parse_args()

    summary_dir = Path(args.summary_dir)
    errors: list[str] = []

    for name in REQUIRED_FILES:
        p = summary_dir / name
        if not p.exists():
            errors.append(f"Missing file: {p}")

    if not errors:
        errors.extend(_check_p4(summary_dir, args.expected_p4_runs))
        errors.extend(_check_d_by_algo(summary_dir, args.expected_d_runs))
        errors.extend(_check_markdown(summary_dir))

    if errors:
        print("SANITY CHECK FAILED")
        for err in errors:
            print(f"- {err}")
        return 1

    print("SANITY CHECK PASSED")
    print(f"summary_dir={summary_dir}")
    print(f"expected_p4_runs={args.expected_p4_runs}")
    print(f"expected_d_runs={args.expected_d_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
