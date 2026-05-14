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

from simulation.stats import bootstrap_ci, wilcoxon_pvalue, wilcoxon_test


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


def _std(values: list[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    mean = _mean(values)
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


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
        avgq_vals = [float(r.get("avg_queue_length", 0.0) or 0.0) for r in g_rows]
        maxq_vals = [float(r.get("max_queue_length", 0.0) or 0.0) for r in g_rows]
        p95q_vals = [float(r.get("p95_queue_length", 0.0) or 0.0) for r in g_rows]

        _, sla_ci_lo, sla_ci_hi = bootstrap_ci(sla_vals, seed=0)
        _, cito_ci_lo, cito_ci_hi = bootstrap_ci(cito_vals, seed=1)
        _, tat_ci_lo, tat_ci_hi = bootstrap_ci(tat_vals, seed=2)
        _, p95_ci_lo, p95_ci_hi = bootstrap_ci(p95_vals, seed=3)
        _, thr_ci_lo, thr_ci_hi = bootstrap_ci(thr_vals, seed=4)
        _, avgq_ci_lo, avgq_ci_hi = bootstrap_ci(avgq_vals, seed=5)
        _, maxq_ci_lo, maxq_ci_hi = bootstrap_ci(maxq_vals, seed=6)
        _, p95q_ci_lo, p95q_ci_hi = bootstrap_ci(p95q_vals, seed=7)

        packed.update(
            {
                "n_records": len(g_rows),
                "n": len(g_rows),  # backward-compatible alias for validators
                "staffing_N": packed.get("n_doctors_sweep"),  # thesis-table alias
                "rho_avg_mean": _round(_mean(rho_vals), 4),
                "rho_normalized_mean": _round(_mean(rho_norm_vals), 4),
                "sla_plan_target_mean": _round(_mean(sla_vals), 4),
                "sla_plan_target_std": _round(_std(sla_vals), 4),
                "sla_plan_target_ci_95_lo": _round(sla_ci_lo, 4),
                "sla_plan_target_ci_95_hi": _round(sla_ci_hi, 4),
                "sla_cito_mean": _round(_mean(cito_vals), 4),
                "sla_cito_std": _round(_std(cito_vals), 4),
                "sla_cito_ci_95_lo": _round(cito_ci_lo, 4),
                "sla_cito_ci_95_hi": _round(cito_ci_hi, 4),
                "tat_median_min_mean": _round(_mean(tat_vals), 4),
                "tat_median_min_std": _round(_std(tat_vals), 4),
                "tat_median_min_ci_95_lo": _round(tat_ci_lo, 4),
                "tat_median_min_ci_95_hi": _round(tat_ci_hi, 4),
                "tat_p95_min_mean": _round(_mean(p95_vals), 4),
                "tat_p95_min_std": _round(_std(p95_vals), 4),
                "tat_p95_min_ci_95_lo": _round(p95_ci_lo, 4),
                "tat_p95_min_ci_95_hi": _round(p95_ci_hi, 4),
                "throughput_per_hour_mean": _round(_mean(thr_vals), 4),
                "throughput_per_hour_std": _round(_std(thr_vals), 4),
                "throughput_per_hour_ci_95_lo": _round(thr_ci_lo, 4),
                "throughput_per_hour_ci_95_hi": _round(thr_ci_hi, 4),
                "avg_queue_length_mean": _round(_mean(avgq_vals), 4),
                "avg_queue_length_std": _round(_std(avgq_vals), 4),
                "avg_queue_length_ci_95_lo": _round(avgq_ci_lo, 4),
                "avg_queue_length_ci_95_hi": _round(avgq_ci_hi, 4),
                "max_queue_length_mean": _round(_mean(maxq_vals), 4),
                "max_queue_length_std": _round(_std(maxq_vals), 4),
                "max_queue_length_ci_95_lo": _round(maxq_ci_lo, 4),
                "max_queue_length_ci_95_hi": _round(maxq_ci_hi, 4),
                "p95_queue_length_mean": _round(_mean(p95q_vals), 4),
                "p95_queue_length_std": _round(_std(p95q_vals), 4),
                "p95_queue_length_ci_95_lo": _round(p95q_ci_lo, 4),
                "p95_queue_length_ci_95_hi": _round(p95q_ci_hi, 4),
            }
        )
        out.append(packed)
    return out


def _write_pairwise_tests(path: Path, rows: list[dict]) -> None:
    by_n_algo: dict[int, dict[str, list[dict]]] = {}
    for row in rows:
        n_doc = int(row.get("n_doctors_sweep", 0) or 0)
        algo = str(row.get("algorithm", ""))
        if not algo:
            continue
        by_n_algo.setdefault(n_doc, {}).setdefault(algo, []).append(row)

    metrics = ("sla_plan_target", "sla_cito", "tat_median_min", "tat_p95_min")
    out_rows: list[dict] = []

    for n_doc, grouped in sorted(by_n_algo.items(), key=lambda kv: kv[0]):
        algos = sorted(grouped.keys())
        for i in range(len(algos)):
            for j in range(i + 1, len(algos)):
                a = algos[i]
                b = algos[j]
                for metric in metrics:
                    xa = [float(r.get(metric, 0.0) or 0.0) for r in grouped[a]]
                    xb = [float(r.get(metric, 0.0) or 0.0) for r in grouped[b]]
                    u_stat, conclusion = wilcoxon_test(xa, xb)
                    p_val = wilcoxon_pvalue(xa, xb)
                    out_rows.append(
                        {
                            "n_doctors_sweep": n_doc,
                            "algorithm_a": a,
                            "algorithm_b": b,
                            "metric": metric,
                            "u_stat": _round(u_stat, 4) if u_stat == u_stat else "",
                            "p_value": _round(p_val, 6) if p_val == p_val else "",
                            "p_value_note": conclusion,
                            "n_a": len(xa),
                            "n_b": len(xb),
                        }
                    )

    if not out_rows:
        return

    fields = [
        "n_doctors_sweep",
        "algorithm_a",
        "algorithm_b",
        "metric",
        "u_stat",
        "p_value",
        "p_value_note",
        "n_a",
        "n_b",
    ]
    _write_csv(path, out_rows, fields)


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
    parser.add_argument(
        "--output-tests",
        default="results/ch5/final_series/summary/appendix_stat_tests.csv",
        help="Output CSV with pairwise Wilcoxon tests per doctor count",
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
        "staffing_N",
        "n_records",
        "n",
        "rho_avg_mean",
        "rho_normalized_mean",
        "sla_plan_target_mean",
        "sla_plan_target_std",
        "sla_plan_target_ci_95_lo",
        "sla_plan_target_ci_95_hi",
        "sla_cito_mean",
        "sla_cito_std",
        "sla_cito_ci_95_lo",
        "sla_cito_ci_95_hi",
        "tat_median_min_mean",
        "tat_median_min_std",
        "tat_median_min_ci_95_lo",
        "tat_median_min_ci_95_hi",
        "tat_p95_min_mean",
        "tat_p95_min_std",
        "tat_p95_min_ci_95_lo",
        "tat_p95_min_ci_95_hi",
        "throughput_per_hour_mean",
        "throughput_per_hour_std",
        "throughput_per_hour_ci_95_lo",
        "throughput_per_hour_ci_95_hi",
        "avg_queue_length_mean",
        "avg_queue_length_std",
        "avg_queue_length_ci_95_lo",
        "avg_queue_length_ci_95_hi",
        "max_queue_length_mean",
        "max_queue_length_std",
        "max_queue_length_ci_95_lo",
        "max_queue_length_ci_95_hi",
        "p95_queue_length_mean",
        "p95_queue_length_std",
        "p95_queue_length_ci_95_lo",
        "p95_queue_length_ci_95_hi",
    ]
    by_algo_fields = [
        "n_doctors_sweep",
        "staffing_N",
        "algorithm",
        "n_records",
        "n",
        "rho_avg_mean",
        "rho_normalized_mean",
        "sla_plan_target_mean",
        "sla_plan_target_std",
        "sla_plan_target_ci_95_lo",
        "sla_plan_target_ci_95_hi",
        "sla_cito_mean",
        "sla_cito_std",
        "sla_cito_ci_95_lo",
        "sla_cito_ci_95_hi",
        "tat_median_min_mean",
        "tat_median_min_std",
        "tat_median_min_ci_95_lo",
        "tat_median_min_ci_95_hi",
        "tat_p95_min_mean",
        "tat_p95_min_std",
        "tat_p95_min_ci_95_lo",
        "tat_p95_min_ci_95_hi",
        "throughput_per_hour_mean",
        "throughput_per_hour_std",
        "throughput_per_hour_ci_95_lo",
        "throughput_per_hour_ci_95_hi",
        "avg_queue_length_mean",
        "avg_queue_length_std",
        "avg_queue_length_ci_95_lo",
        "avg_queue_length_ci_95_hi",
        "max_queue_length_mean",
        "max_queue_length_std",
        "max_queue_length_ci_95_lo",
        "max_queue_length_ci_95_hi",
        "p95_queue_length_mean",
        "p95_queue_length_std",
        "p95_queue_length_ci_95_lo",
        "p95_queue_length_ci_95_hi",
    ]

    out_pooled = Path(args.output_pooled)
    out_by_algo = Path(args.output_by_algo)
    _write_csv(out_pooled, pooled, pooled_fields)
    _write_csv(out_by_algo, by_algo, by_algo_fields)
    _write_pairwise_tests(Path(args.output_tests), rows)

    # Minimal N* recommendation (first N with SLA >= 0.90 on pooled mean)
    n_star = None
    for row in sorted(pooled, key=lambda x: int(x["n_doctors_sweep"])):
        if float(row["sla_plan_target_mean"]) >= 0.90:
            n_star = int(row["n_doctors_sweep"])
            break

    print(f"Collected rows: {len(rows)}")
    print(f"Pooled table: {out_pooled}")
    print(f"By-algorithm table: {out_by_algo}")
    print(f"Pairwise tests: {args.output_tests}")
    if n_star is not None:
        print(f"N_min empirical: {n_star}; N_target (N* + 1): {n_star + 1}")
    else:
        print("N_min empirical not reached in available D sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
