"""
exporter.py — подготовка агрегатов и сырых выборок для рисунков/таблиц главы 5.

Вход: summary JSONL (канонический формат из simulation.simulator.SimulationResult).
Выход:
  - aggregated_by_algo_scenario.csv  (mean/median по метрикам)
  - replications_raw.csv             (сырые репликации для boxplot/Pareto)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    n = len(vals)
    m = n // 2
    return vals[m] if n % 2 == 1 else (vals[m - 1] + vals[m]) / 2.0


def _to_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def export_raw_replications(records: list[dict], output_csv: str) -> None:
    """Сохраняет сырые репликации, достаточные для boxplot и Pareto-front."""
    fields = [
        "scenario", "algorithm", "replication", "seed",
        "sla_cito", "sla_plan_target", "sla_plan_max",
        "tat_median_min", "tat_p95_min", "sigma_w2", "rho_avg", "rho_normalized",
        "throughput_per_hour", "avg_queue_length", "max_queue_length", "p95_queue_length",
        "completed_tasks",
    ]
    os.makedirs(os.path.dirname(output_csv) if os.path.dirname(output_csv) else ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            w.writerow({k: rec.get(k, "") for k in fields})


def export_aggregated(records: list[dict], output_csv: str) -> None:
    """Сохраняет агрегаты mean/median по (scenario, algorithm)."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in records:
        grouped[(rec.get("scenario", "unknown"), rec.get("algorithm", "unknown"))].append(rec)

    fields = [
        "scenario", "algorithm", "n",
        "n_valid_plan", "n_valid_cito", "n_valid_tat",
        "sla_cito_mean", "sla_plan_target_mean", "sla_plan_max_mean",
        "tat_median_min_mean", "tat_median_min_median", "tat_p95_min_mean",
        "sigma_w2_mean", "rho_avg_mean", "rho_normalized_mean", "throughput_per_hour_mean",
        "avg_queue_length_mean", "max_queue_length_mean", "p95_queue_length_mean",
    ]

    os.makedirs(os.path.dirname(output_csv) if os.path.dirname(output_csv) else ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for (scenario, algorithm), rows in sorted(grouped.items()):
            plan_rows = [
                r for r in rows
                if bool(r.get("valid_plan_sample", False)) or int(r.get("plan_sample_size", 0) or 0) > 0
            ]
            cito_rows = [
                r for r in rows
                if bool(r.get("valid_cito_sample", False)) or int(r.get("cito_sample_size", 0) or 0) > 0
            ]
            tat_rows = [
                r for r in rows
                if bool(r.get("valid_tat_sample", False))
                or int(r.get("tat_sample_size", 0) or 0) > 0
                or int(r.get("completed_tasks", 0) or 0) > 0
            ]

            sla_cito = [_to_float(r.get("sla_cito")) for r in cito_rows]
            sla_plan_t = [_to_float(r.get("sla_plan_target")) for r in plan_rows]
            sla_plan_m = [_to_float(r.get("sla_plan_max")) for r in plan_rows]
            tat_med = [_to_float(r.get("tat_median_min")) for r in tat_rows]
            tat_p95 = [_to_float(r.get("tat_p95_min")) for r in tat_rows]
            sig = [_to_float(r.get("sigma_w2")) for r in rows]
            rho = [_to_float(r.get("rho_avg")) for r in rows]
            rho_norm = [_to_float(r.get("rho_normalized", r.get("rho_avg"))) for r in rows]
            thr = [_to_float(r.get("throughput_per_hour")) for r in tat_rows]
            q_avg = [_to_float(r.get("avg_queue_length")) for r in rows]
            q_max = [_to_float(r.get("max_queue_length")) for r in rows]
            q_p95 = [_to_float(r.get("p95_queue_length")) for r in rows]

            w.writerow({
                "scenario": scenario,
                "algorithm": algorithm,
                "n": len(rows),
                "n_valid_plan": len(plan_rows),
                "n_valid_cito": len(cito_rows),
                "n_valid_tat": len(tat_rows),
                "sla_cito_mean": round(_mean(sla_cito), 4),
                "sla_plan_target_mean": round(_mean(sla_plan_t), 4),
                "sla_plan_max_mean": round(_mean(sla_plan_m), 4),
                "tat_median_min_mean": round(_mean(tat_med), 4),
                "tat_median_min_median": round(_median(tat_med), 4),
                "tat_p95_min_mean": round(_mean(tat_p95), 4),
                "sigma_w2_mean": round(_mean(sig), 6),
                "rho_avg_mean": round(_mean(rho), 4),
                "rho_normalized_mean": round(_mean(rho_norm), 4),
                "throughput_per_hour_mean": round(_mean(thr), 4),
                "avg_queue_length_mean": round(_mean(q_avg), 4),
                "max_queue_length_mean": round(_mean(q_max), 4),
                "p95_queue_length_mean": round(_mean(q_p95), 4),
            })


def main() -> None:
    p = argparse.ArgumentParser(description="Экспорт агрегатов и сырых репликаций для главы 5")
    p.add_argument("--input", default="results/summary/sim_results.jsonl", help="Входной summary JSONL")
    p.add_argument("--raw-csv", default="results/plots_input/replications_raw.csv", help="Выходной CSV сырых репликаций")
    p.add_argument("--agg-csv", default="results/plots_input/aggregated_by_algo_scenario.csv", help="Выходной CSV агрегатов")
    args = p.parse_args()

    records = load_jsonl(args.input)
    export_raw_replications(records, args.raw_csv)
    export_aggregated(records, args.agg_csv)
    print(f"Raw replications: {args.raw_csv}")
    print(f"Aggregated table: {args.agg_csv}")


if __name__ == "__main__":
    main()
