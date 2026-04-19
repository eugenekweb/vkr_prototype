"""Collect chapter-5 D-sweep results into pooled and per-algorithm CSV tables.

Examples:
  python scripts/collect_ch5_results.py --input-dir results/ch5/d_sweep
  python scripts/collect_ch5_results.py --rebuild
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _round(x: float, ndigits: int = 4) -> float:
    return round(float(x), ndigits)


def _extract_n(path: Path) -> int | None:
    m = re.search(r"d(\d+)", path.stem.lower())
    return int(m.group(1)) if m else None


def _collect_rows(input_dir: Path) -> list[dict]:
    files = sorted(input_dir.glob("d*_*.jsonl"))
    if not files:
        files = sorted(input_dir.glob("d*.jsonl"))

    rows: list[dict] = []
    for file in files:
        n_doctors = _extract_n(file)
        for rec in _load_jsonl(file):
            row = dict(rec)
            if n_doctors is not None:
                row["n_doctors_sweep"] = n_doctors
            else:
                row["n_doctors_sweep"] = int(rec.get("num_doctors", 0) or 0)
            rows.append(row)
    return rows


def _group_mean(rows: list[dict], key_fields: list[str]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(row.get(k) for k in key_fields)
        groups.setdefault(key, []).append(row)

    out: list[dict] = []
    for key, g_rows in sorted(groups.items(), key=lambda kv: kv[0]):
        packed = {k: v for k, v in zip(key_fields, key)}
        rho_vals = [float(r.get("rho_avg", 0.0) or 0.0) for r in g_rows]
        rho_norm_vals = [float(r.get("rho_normalized", r.get("rho_avg", 0.0)) or 0.0) for r in g_rows]
        sla_vals = [float(r.get("sla_plan_target", 0.0) or 0.0) for r in g_rows]
        cito_vals = [float(r.get("sla_cito", 0.0) or 0.0) for r in g_rows]
        tat_vals = [float(r.get("tat_median_min", 0.0) or 0.0) for r in g_rows]
        p95_vals = [float(r.get("tat_p95_min", 0.0) or 0.0) for r in g_rows]
        thr_vals = [float(r.get("throughput_per_hour", 0.0) or 0.0) for r in g_rows]

        packed.update(
            {
                "n_records": len(g_rows),
                "rho_avg_mean": _round(_mean(rho_vals), 4),
                "rho_normalized_mean": _round(_mean(rho_norm_vals), 4),
                "sla_plan_target_mean": _round(_mean(sla_vals), 4),
                "sla_cito_mean": _round(_mean(cito_vals), 4),
                "tat_median_min_mean": _round(_mean(tat_vals), 4),
                "tat_p95_min_mean": _round(_mean(p95_vals), 4),
                "throughput_per_hour_mean": _round(_mean(thr_vals), 4),
            }
        )
        out.append(packed)
    return out


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect D-sweep chapter 5 results")
    parser.add_argument("--input-dir", default="results/ch5/d_sweep", help="Directory with d*.jsonl")
    parser.add_argument(
        "--output-pooled",
        default="results/ch5/final_series/summary/final_table_d2_d12_pooled.csv",
        help="Output CSV pooled by doctor count",
    )
    parser.add_argument(
        "--output-by-algo",
        default="results/ch5/final_series/summary/final_table_d2_d12_by_algo.csv",
        help="Output CSV grouped by doctor count and algorithm",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Use default paths for full rebuild (input-dir/results/ch5/d_sweep and final outputs)",
    )
    args = parser.parse_args()

    if args.rebuild:
        args.input_dir = "results/ch5/d_sweep"
        args.output_pooled = "results/ch5/final_series/summary/final_table_d2_d12_pooled.csv"
        args.output_by_algo = "results/ch5/final_series/summary/final_table_d2_d12_by_algo.csv"

    input_dir = Path(args.input_dir)
    rows = _collect_rows(input_dir)
    if not rows:
        print(f"No D-sweep JSONL files found in: {input_dir}")
        return 2

    pooled = _group_mean(rows, ["n_doctors_sweep"])
    by_algo = _group_mean(rows, ["n_doctors_sweep", "algorithm"])

    pooled_fields = [
        "n_doctors_sweep",
        "n_records",
        "rho_avg_mean",
        "rho_normalized_mean",
        "sla_plan_target_mean",
        "sla_cito_mean",
        "tat_median_min_mean",
        "tat_p95_min_mean",
        "throughput_per_hour_mean",
    ]
    by_algo_fields = [
        "n_doctors_sweep",
        "algorithm",
        "n_records",
        "rho_avg_mean",
        "rho_normalized_mean",
        "sla_plan_target_mean",
        "sla_cito_mean",
        "tat_median_min_mean",
        "tat_p95_min_mean",
        "throughput_per_hour_mean",
    ]

    out_pooled = Path(args.output_pooled)
    out_by_algo = Path(args.output_by_algo)
    _write_csv(out_pooled, pooled, pooled_fields)
    _write_csv(out_by_algo, by_algo, by_algo_fields)

    # Minimal N* recommendation (first N with SLA >= 0.90 on pooled mean)
    n_star = None
    for row in sorted(pooled, key=lambda x: int(x["n_doctors_sweep"])):
        if float(row["sla_plan_target_mean"]) >= 0.90:
            n_star = int(row["n_doctors_sweep"])
            break

    print(f"Collected rows: {len(rows)}")
    print(f"Pooled table: {out_pooled}")
    print(f"By-algorithm table: {out_by_algo}")
    if n_star is not None:
        print(f"N_min empirical: {n_star}; N_target (N* + 1): {n_star + 1}")
    else:
        print("N_min empirical not reached in available D sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
