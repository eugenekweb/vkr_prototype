"""Статистический анализ результатов симуляционных прогонов."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from collections import defaultdict
from typing import Optional

# Поля, обязательные в JSONL-записях прогонов
_REQUIRED_FIELDS = [
    "scenario", "algorithm", "assignment_strategy", "seed",
    "sla_cito", "sla_plan_target", "sla_plan_max",
    "sigma_w2", "rho_avg", "rho_normalized",
    "tat_median_min", "tat_mean_min", "tat_p95_min",
    "throughput_per_hour", "completed_tasks",
]

# Метрики для сводного вывода
_SUMMARY_METRICS = [
    "sla_plan_target", "sla_cito", "tat_p95_min",
    "sigma_w2", "rho_avg", "rho_normalized", "throughput_per_hour",
]


def _normalize_record(rec: dict) -> dict:
    """Нормализует legacy-ключи к каноническому snake_case формату."""
    out = dict(rec)
    out.setdefault("sla_cito", out.get("SLA_CITO_target"))
    out.setdefault("sla_plan_target", out.get("SLA_plan_target"))
    out.setdefault("sla_plan_max", out.get("SLA_plan_max"))
    out.setdefault("sigma_w2", out.get("load_variance"))
    out.setdefault("tat_median_min", out.get("median_TAT_min"))
    out.setdefault("tat_mean_min", out.get("mean_TAT_min"))
    out.setdefault("tat_p95_min", out.get("TAT_p95_min"))
    out.setdefault("rho_normalized", out.get("rho_avg"))
    return out


def load_jsonl(path: str) -> list[dict]:
    """Читает JSONL-файл с результатами прогонов."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(_normalize_record(json.loads(line)))
    return records


def jsonl_to_csv(
    records: list[dict],
    csv_path: str,
    fields: Optional[list[str]] = None,
) -> None:
    """Экспортирует список записей в CSV.

    Args:
        records:  список dict из JSONL
        csv_path: путь к выходному CSV
        fields:   список полей; по умолчанию _REQUIRED_FIELDS
    """
    if not records:
        return
    cols = fields or _REQUIRED_FIELDS
    # Добавляем поля, которые есть хотя бы в одной записи
    extra = [k for k in records[0] if k not in cols and k != "doctors_by_modality"]
    cols = cols + [e for e in extra if e not in cols]

    os.makedirs(os.path.dirname(csv_path) if os.path.dirname(csv_path) else ".", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in cols})


def bootstrap_ci(
    values: list[float],
    stat_fn=None,
    confidence: float = 0.95,
    n_boot: int = 10_000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """
    Bootstrap доверительный интервал для статистики stat_fn.

    Args:
        values:     выборка значений (репликации)
        stat_fn:    функция статистики; по умолчанию среднее
        confidence: уровень доверия (0.95 → 95% CI)
        n_boot:     число bootstrap-выборок
        seed:       зерно для воспроизводимости

    Returns:
        (point_estimate, lower, upper)
    """
    if not values:
        return (float("nan"),) * 3
    def _mean(x):
        return sum(x) / len(x)

    if stat_fn is None:
        stat_fn = _mean

    rng = random.Random(seed)
    n = len(values)
    point = stat_fn(values)
    boot_stats = []
    for _ in range(n_boot):
        sample = [rng.choice(values) for _ in range(n)]
        boot_stats.append(stat_fn(sample))

    boot_stats.sort()
    alpha = 1.0 - confidence
    lo_idx = int(alpha / 2 * n_boot)
    hi_idx = int((1.0 - alpha / 2) * n_boot)
    lo = boot_stats[max(0, lo_idx)]
    hi = boot_stats[min(n_boot - 1, hi_idx)]
    return (point, lo, hi)


def wilcoxon_test(
    x: list[float],
    y: list[float],
) -> tuple[float, str]:
    """Критерий Вилкоксона–Манна–Уитни (двусторонний).

    Args:
        x, y: две независимые выборки (репликации двух алгоритмов)

    Returns:
        (U-статистика, интерпретация: p < 0.05 или нет)

    Примечание: реализована аппроксимация нормальным распределением
    для n1, n2 > 8 (достаточно для 30 репликаций).
    """
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return (float("nan"), "insufficient data")

    # Ранги объединённой выборки
    combined = [(v, 0) for v in x] + [(v, 1) for v in y]
    combined.sort(key=lambda t: t[0])
    ranks = []
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for _ in range(j - i):
            ranks.append(avg_rank)
        i = j

    r1 = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    U1 = r1 - n1 * (n1 + 1) / 2.0
    U2 = n1 * n2 - U1
    U = min(U1, U2)

    # Нормальная аппроксимация
    mean_u = n1 * n2 / 2.0
    std_u = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if std_u == 0:
        return (U, "std=0, cannot compute")
    z = (U - mean_u) / std_u
    # p-value (двустороннее): P(|Z| > |z|) ≈ 2 × (1 − Φ(|z|))
    p_approx = 2.0 * _normal_sf(abs(z))
    conclusion = "p < 0.05 (значимо)" if p_approx < 0.05 else f"p ≈ {p_approx:.3f} (незначимо)"
    return (U, conclusion)


def _normal_sf(z: float) -> float:
    """Survival function стандартного нормального: P(Z > z). Аппроксимация Abramowitz & Stegun."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def compare_algorithms(
    records: list[dict],
    metrics: Optional[list[str]] = None,
    group_by: str = "algorithm",
) -> dict[str, dict]:
    """
    Группирует записи по group_by и вычисляет для каждой группы:
    - mean, std, bootstrap 95% CI для каждой метрики.

    Args:
        records:  список записей JSONL
        metrics:  список метрик; по умолчанию _SUMMARY_METRICS
        group_by: поле группировки (обычно "algorithm" или "assignment_strategy")

    Returns:
        dict: group_value → {metric → {mean, std, ci_lo, ci_hi}}
    """
    if metrics is None:
        metrics = _SUMMARY_METRICS

    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        key = rec.get(group_by, "unknown")
        groups[key].append(rec)

    result = {}
    for group, recs in groups.items():
        result[group] = {}
        for metric in metrics:
            vals = [r[metric] for r in recs if metric in r and r[metric] is not None]
            if not vals:
                result[group][metric] = {"mean": None, "std": None, "ci_lo": None, "ci_hi": None}
                continue
            mean = sum(vals) / len(vals)
            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1))
            _, ci_lo, ci_hi = bootstrap_ci(vals)
            result[group][metric] = {
                "mean": round(mean, 4),
                "std": round(std, 4),
                "ci_lo": round(ci_lo, 4),
                "ci_hi": round(ci_hi, 4),
                "n": len(vals),
            }
    return result


def print_comparison_table(
    comparison: dict[str, dict],
    metrics: Optional[list[str]] = None,
) -> None:
    """Выводит сводную таблицу сравнения в консоль."""
    if metrics is None:
        metrics = _SUMMARY_METRICS
    groups = sorted(comparison.keys())

    header = f"{'Метрика':<22}" + "".join(f"  {g:<22}" for g in groups)
    print(header)
    print("-" * len(header))

    for metric in metrics:
        row = f"{metric:<22}"
        for g in groups:
            m = comparison.get(g, {}).get(metric)
            if m and m.get("mean") is not None:
                row += (
                    f"  {m['mean']:.4f} [{m['ci_lo']:.4f},{m['ci_hi']:.4f}] "
                )
            else:
                row += "  —" + " " * 22
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Статистический анализ результатов экспериментов")
    parser.add_argument(
        "--input", default="results/sim_results.jsonl",
        help="JSONL-файл с результатами прогонов",
    )
    parser.add_argument(
        "--csv", default=None,
        help="Экспортировать в CSV (если не задан — пропустить)",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Вывести сводную таблицу сравнения по алгоритмам",
    )
    parser.add_argument(
        "--group-by", default="algorithm", dest="group_by",
        help="Поле группировки для --compare (default: algorithm)",
    )
    parser.add_argument(
        "--wilcoxon", nargs=2, metavar=("GROUP_A", "GROUP_B"),
        help="Критерий Вилкоксона между двумя группами (напр. EDF FIFO)",
    )
    parser.add_argument(
        "--metric", default="sla_plan_target",
        help="Метрика для --wilcoxon (default: SLA_plan_target)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Зерно bootstrap (default: 0)",
    )

    args = parser.parse_args()

    records = load_jsonl(args.input)
    print(f"Загружено {len(records)} записей из {args.input}")

    if args.csv:
        jsonl_to_csv(records, args.csv)
        print(f"CSV сохранён: {args.csv}")

    if args.compare:
        comparison = compare_algorithms(records, group_by=args.group_by)
        print(f"\nСравнение по {args.group_by}:")
        print_comparison_table(comparison)

    if args.wilcoxon:
        ga, gb = args.wilcoxon
        metric = args.metric
        groups: dict[str, list] = defaultdict(list)
        for rec in records:
            key = rec.get(args.group_by, "unknown")
            if metric in rec and rec[metric] is not None:
                groups[key].append(float(rec[metric]))
        xa = groups.get(ga, [])
        xb = groups.get(gb, [])
        if not xa or not xb:
            print(f"Нет данных для {ga} или {gb} по метрике {metric}")
        else:
            U, conclusion = wilcoxon_test(xa, xb)
            pt_a, lo_a, hi_a = bootstrap_ci(xa, seed=args.seed)
            pt_b, lo_b, hi_b = bootstrap_ci(xb, seed=args.seed)
            print(f"\nКритерий Вилкоксона: {ga} vs {gb} по '{metric}'")
            print(f"  {ga}: mean={pt_a:.4f} 95%CI=[{lo_a:.4f},{hi_a:.4f}] (n={len(xa)})")
            print(f"  {gb}: mean={pt_b:.4f} 95%CI=[{lo_b:.4f},{hi_b:.4f}] (n={len(xb)})")
            print(f"  U={U:.1f}, {conclusion}")


if __name__ == "__main__":
    main()
