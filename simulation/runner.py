"""Batch-runner экспериментального контура.

CLI:
    python -m simulation.runner \\
        --algorithm EDF \\
        --days 1 \\
        --arrival-rate 446 \\
        --seed 42 \\
        --n-runs 10 \\
        --output results/edf_baseline.jsonl

N повторений: seed = base_seed + run_index (для доверительных интервалов).
JSONL-вывод: один объект на строку.
По умолчанию output перезаписывается (очищается перед записью).
Для дозаписи используйте флаг --append-output.

Именованные сценарии:
    --scenario baseline       базовый P2 (lambda=446/д, thinning)
    --scenario growth20       плановый рост P4 (lambda=535/д, +20%)
    --scenario cito-burst     P3: 15 CITO в t=4ч, интервал 4 мин (детерм.)
    --scenario doctor-outage  недоступность doc_001, 60 мин с t=60-й
    --scenario validation     P1: верификация (20 заданий, 1 врач)
    --scenario mmc-validation однородный M/M/c vs Erlang C (плоский профиль)

Параметры сценариев можно перекрыть явными флагами:
    --doctor-outage doc_001 --outage-start 60 --outage-duration 60
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Optional

import yaml


def _load_config(path: str = "config/config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _apply_simulation_mode(config: dict, mode: Optional[str] = None) -> tuple[dict, str]:
    """Возвращает конфиг, нормализованный под выбранный режим симуляции."""
    resolved = dict(config)
    sim_cfg = dict(resolved.get("simulation", {}))
    modes = sim_cfg.get("modes", {}) or {}
    selected_mode = mode or sim_cfg.get("mode", "evaluation")
    profile = modes.get(selected_mode, {}) or {}

    for key, value in profile.items():
        if key == "modes":
            continue
        sim_cfg[key] = value

    sim_cfg["mode"] = selected_mode
    resolved["simulation"] = sim_cfg
    return resolved, selected_mode


def _slug(value: str) -> str:
    return value.replace("/", "-").replace(" ", "-").lower()


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _resolve_output_layout(output: str) -> dict:
    """Формирует канонические директории артефактов.

    output трактуется как summary JSONL. Остальные пути вычисляются рядом.
    """
    output_path = Path(output)
    if output_path.parent.name == "summary":
        root = output_path.parent.parent
    else:
        root = output_path.parent if str(output_path.parent) not in ("", ".") else Path("results")

    summary_dir = root / "summary"
    audit_dir = root / "audit"
    plots_dir = root / "plots_input"
    summary_path = summary_dir / output_path.name

    for d in (summary_dir, audit_dir, plots_dir):
        d.mkdir(parents=True, exist_ok=True)

    return {
        "root": str(root),
        "summary_dir": str(summary_dir),
        "audit_dir": str(audit_dir),
        "plots_dir": str(plots_dir),
        "summary_path": str(summary_path),
    }


def _warn_if_algorithms_not_distinguishable(records: list[dict], threshold: float = 0.01) -> list[str]:
    """Проверяет, различаются ли алгоритмы по ключевым метрикам."""
    by_algo: dict[str, list[dict]] = {}
    for rec in records:
        by_algo.setdefault(rec.get("algorithm", "unknown"), []).append(rec)

    if len(by_algo) < 2:
        return []

    def _mean(metric: str, rows: list[dict]) -> float:
        vals = [float(r[metric]) for r in rows if metric in r and r[metric] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    warnings: list[str] = []
    metrics = ("sla_plan_target", "sla_cito", "tat_p95_min", "sigma_w2")
    for metric in metrics:
        means = [_mean(metric, rows) for rows in by_algo.values()]
        if not means:
            continue
        spread = max(means) - min(means)
        if spread < threshold:
            warnings.append(
                f"Metric '{metric}' spread={spread:.4f} < threshold={threshold:.4f}; "
                "scenario may be weakly distinguishing."
            )
    return warnings


def _resolve_scenario_preset(presets: dict, requested: str) -> tuple[str, dict]:
    """Возвращает (canonical_name, preset) с поддержкой алиасов baselineCH5/baseline_ch5."""
    if requested in presets:
        return requested, presets[requested]

    def _canon(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    requested_key = _canon(requested)
    for key, value in presets.items():
        if _canon(key) == requested_key:
            return key, value

    raise ValueError(f"Unknown scenario preset: {requested}")


def run_single(
    algorithm: str,
    seed: int,
    days: float,
    arrival_rate: float,
    config: dict,
    output_path: str,
    audit_mode: str,
    audit_dir: str,
    run_index: int = 0,
    num_doctors: Optional[int] = None,
    doctor_outage_id: str = "",
    outage_start_min: float = 0.0,
    outage_duration_min: float = 0.0,
    scenario: str = "",
    assignment_strategy: str = "wll",
    allow_synthetic: bool = False,
    burst_size: int = 15,
    burst_start_min: float = 240.0,
    burst_interval_min: float = 4.0,
    burst_duration_min: Optional[float] = None,
) -> dict:
    """Один прогон имитационной модели."""
    from algorithms.base import AlgorithmConfig
    from simulation.simulator import Simulator

    algo_cfg = dict(config.get("algorithm", {}))
    algo_cfg["type"] = algorithm

    params = AlgorithmConfig.from_dict(algo_cfg)
    scenario_label = _slug(scenario or "manual")
    algo_label = _slug(algorithm)
    if audit_mode == "none":
        sim_jsonl = None
    elif audit_mode == "sample":
        sim_jsonl = os.path.join(audit_dir, f"{scenario_label}_{algo_label}.jsonl")
    else:
        sim_jsonl = os.path.join(
            audit_dir,
            f"{scenario_label}_{algo_label}_seed{seed}_rep{run_index}.jsonl",
        )

    simulator = Simulator(
        algorithm_type=algorithm,
        params=params,
        seed=seed,
        config=config,
        jsonl_path=sim_jsonl,
        audit_mode=audit_mode,
        num_doctors_override=num_doctors,
        scenario=scenario,
        assignment_strategy=assignment_strategy,
        allow_synthetic=allow_synthetic,
    )

    if scenario == "cito-burst":
        simulator._inject_cito_burst(
            n_tasks=burst_size,
            start_min=burst_start_min,
            interval_min=burst_interval_min,
            duration_min=burst_duration_min,
        )

    if doctor_outage_id and outage_duration_min > 0:
        for doc in simulator._doctors:
            if doc.id == doctor_outage_id or doc.id == f"sim-{doctor_outage_id}":
                def _outage(env, d, start, dur):
                    yield env.timeout(start)
                    d.is_outage = True
                    d.is_available = False
                    simulator.audit.log_event_sync(
                        event_type="DOCTOR_UNAVAILABLE",
                        actor=d.id,
                        payload={"from_t": start, "duration": dur},
                    )
                    yield env.timeout(dur)
                    d.is_outage = False
                    # Возвращаем в строй только если врач завершил текущее задание (current_load==0)
                    if d.current_load == 0.0:
                        d.is_available = True
                    simulator.audit.log_event_sync(
                        event_type="DOCTOR_AVAILABLE",
                        actor=d.id,
                        payload={"at_t": start + dur, "load_at_restore": d.current_load},
                    )
                simulator.env.process(_outage(simulator.env, doc, outage_start_min, outage_duration_min))

    duration_min = days * 8 * 60.0
    result = simulator.run_with_rate(duration_min, arrival_rate)
    record = result.to_jsonl_record()
    record["run"] = run_index
    record["replication"] = run_index
    record["seed"] = seed
    record["scenario"] = scenario or "manual"

    _ensure_parent(output_path)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-runner экспериментального контура СУЗ ЦДО"
    )
    parser.add_argument("--algorithm", "--algo", default="EDF",
                        choices=["FIFO", "PQ", "AGING", "EDF", "HYBRID", "all"],
                        help="Алгоритм приоритизации (или all для пакетного сравнения)")
    parser.add_argument("--days", type=float, default=30,
                        help="Длительность прогона в рабочих днях (8 ч)")
    parser.add_argument("--arrival-rate", type=float, default=None,
                        dest="arrival_rate",
                        help="Интенсивность lambda, зад/день (baseline=446, growth=535); из config по умолчанию")
    parser.add_argument("--seed", type=int, default=42,
                        help="Базовое зерно генератора (база для n-runs)")
    parser.add_argument("--n-runs", "--replications", type=int, default=1, dest="n_runs",
                        help="Число повторений для доверительных интервалов")
    parser.add_argument("--output", default="results/sim_results.jsonl",
                        help="Путь к JSONL-файлу результатов")
    parser.add_argument(
        "--append-output",
        action="store_true",
        help="Не очищать выходной JSONL перед запуском (по умолчанию файл перезаписывается)",
    )
    parser.add_argument(
        "--audit",
        choices=["none", "sample", "full"],
        default=None,
        help="Режим audit-логов: none | sample | full (по умолчанию из config)",
    )
    parser.add_argument("--config", default="config/config.yaml",
                        help="Путь к config.yaml")
    parser.add_argument(
        "--scenario-preset",
        default=None,
        help="Имя preset-сценария из config.simulation.scenario_presets",
    )
    parser.add_argument(
        "--strict-distinguishability",
        action="store_true",
        help=(
            "Жёсткий режим: если алгоритмы "
            "слабо различимы (spread < threshold), завершить с кодом 2"
        ),
    )
    parser.add_argument(
        "--no-strict-distinguishability",
        action="store_true",
        help=(
            "Отключить strict-проверку различимости для текущего запуска, "
            "даже если она включена в config"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["evaluation", "operational"],
        default=None,
        help=(
            "Режим симуляции: evaluation для научной оценки алгоритмов, "
            "operational для имитации реального процесса и small-flow прогонов"
        ),
    )
    parser.add_argument("--num-doctors", type=int, default=None, dest="num_doctors",
                        help="Переопределить размер пула врачей (doctor_pool.size в config)")
    parser.add_argument(
        "--scenario",
        choices=[
            "baseline", "growth20", "load_growth",
            "cito-burst", "cito_burst",
            "doctor-outage", "doctor_outage",
            "validation",
            "mmc-validation", "mmc_validation",
        ],
        default=None,
        help=(
            "Именованный сценарий: "
            "baseline (P2, lambda=446); growth20 (P4, lambda=535); "
            "cito-burst (P3, 15 CITO в t=4ч); doctor-outage; "
            "validation (P1); mmc-validation (M/M/c, Erlang C)"
        ),
    )
    parser.add_argument("--doctor-outage", type=str, default="", dest="doctor_outage")
    parser.add_argument("--outage-start", type=float, default=60.0, dest="outage_start")
    parser.add_argument("--outage-duration", type=float, default=60.0, dest="outage_duration")
    parser.add_argument("--burst-size", type=int, default=None, dest="burst_size")
    parser.add_argument("--burst-start", type=float, default=None, dest="burst_start")
    parser.add_argument("--burst-interval", type=float, default=None, dest="burst_interval")
    parser.add_argument("--burst-duration", type=float, default=None, dest="burst_duration")
    parser.add_argument(
        "--assignment-strategy",
        choices=["wll", "round-robin"],
        default="wll",
        dest="assignment_strategy",
        help="Стратегия назначения врача: wll | round-robin",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Разрешить synthetic doctor_pool в operational режиме (только для теоретических сценариев)",
    )

    args = parser.parse_args()
    if args.strict_distinguishability and args.no_strict_distinguishability:
        parser.error("Use either --strict-distinguishability or --no-strict-distinguishability, not both.")
    cli_flags = {token.split("=")[0] for token in sys.argv[1:] if token.startswith("--")}
    config = _load_config(args.config)
    config, active_mode = _apply_simulation_mode(config, args.mode)
    layout = _resolve_output_layout(args.output)
    args.output = layout["summary_path"]

    sim_cfg = config.get("simulation", {})
    logging_cfg = config.get("logging", {})
    args.audit = args.audit or logging_cfg.get("batch_audit_mode", "full")
    strict_dist_cfg = bool(sim_cfg.get("strict_distinguishability", False))
    if args.no_strict_distinguishability:
        strict_dist = False
    elif args.strict_distinguishability:
        strict_dist = True
    else:
        strict_dist = strict_dist_cfg

    print(f"Using simulation mode: {active_mode}")

    scenario_presets = sim_cfg.get("scenario_presets", {})
    if args.scenario_preset:
        preset_name, preset = _resolve_scenario_preset(scenario_presets, args.scenario_preset)

        def _set_from_preset(flag_names: tuple[str, ...], attr: str, key: str) -> None:
            if any(flag in cli_flags for flag in flag_names):
                return
            if key in preset:
                setattr(args, attr, preset[key])

        _set_from_preset(("--scenario",), "scenario", "scenario")
        _set_from_preset(("--arrival-rate",), "arrival_rate", "arrival_rate")
        _set_from_preset(("--days",), "days", "days")
        _set_from_preset(("--n-runs", "--replications"), "n_runs", "n_runs")
        _set_from_preset(("--num-doctors",), "num_doctors", "num_doctors")
        _set_from_preset(("--doctor-outage",), "doctor_outage", "doctor_outage")
        _set_from_preset(("--outage-start",), "outage_start", "outage_start")
        _set_from_preset(("--outage-duration",), "outage_duration", "outage_duration")
        _set_from_preset(("--burst-size",), "burst_size", "burst_size")
        _set_from_preset(("--burst-start",), "burst_start", "burst_start")
        _set_from_preset(("--burst-interval",), "burst_interval", "burst_interval")
        _set_from_preset(("--burst-duration",), "burst_duration", "burst_duration")
        print(f"Using scenario preset: {preset_name}")

    baseline_rate = sim_cfg.get("baseline_arrival_rate", 446)
    growth_rate = sim_cfg.get("growth_arrival_rate", 535)

    if args.arrival_rate is None:
        args.arrival_rate = baseline_rate

    # Применяем настройки именованного сценария
    if args.scenario == "load_growth":
        args.scenario = "growth20"
    if args.scenario == "cito_burst":
        args.scenario = "cito-burst"
    if args.scenario == "doctor_outage":
        args.scenario = "doctor-outage"
    if args.scenario == "mmc_validation":
        args.scenario = "mmc-validation"

    cli_arrival_rate_set = "--arrival-rate" in cli_flags

    if args.scenario == "baseline":
        if not cli_arrival_rate_set:
            args.arrival_rate = baseline_rate
    elif args.scenario == "growth20":
        if not cli_arrival_rate_set:
            args.arrival_rate = growth_rate
    elif args.scenario == "cito-burst":
        if not cli_arrival_rate_set:
            args.arrival_rate = baseline_rate
        args.burst_size = args.burst_size if args.burst_size is not None else 15
        args.burst_start = args.burst_start if args.burst_start is not None else 240.0
        args.burst_interval = args.burst_interval if args.burst_interval is not None else 4.0
    elif args.scenario == "doctor-outage":
        if not args.doctor_outage:
            args.doctor_outage = "doc_001"
    elif args.scenario == "validation":
        args.arrival_rate = 0  # задания вводятся вручную в _run_validation
        args.days = 1                       # длительность не важна, _run_validation управляет
        args.n_runs = 1                     # только один прогон
    elif args.scenario == "mmc-validation":
        if not cli_arrival_rate_set:
            args.arrival_rate = baseline_rate

    # По умолчанию работаем в режиме overwrite, чтобы исключить загрязнение старыми прогонами.
    if os.path.exists(args.output) and not args.append_output:
        os.remove(args.output)

    pool_size = args.num_doctors or len(config.get("sim_doctors", [])) or config.get("doctor_pool", {}).get("size", "?")
    scenario_label = args.scenario or "manual"
    algorithms = ["FIFO", "PQ", "AGING", "EDF", "HYBRID"] if args.algorithm == "all" else [args.algorithm]

    all_summaries = []
    for algo in algorithms:
        print(f"Run: algo={algo}, strategy={args.assignment_strategy}, "
              f"scenario={scenario_label}, rate={args.arrival_rate}/day, days={args.days}, "
              f"runs={args.n_runs}, seed={args.seed}, doctors={pool_size}, audit={args.audit}")
        summaries = []
        for i in range(args.n_runs):
            seed = args.seed + i
            record = run_single(
                algorithm=algo,
                seed=seed,
                days=args.days,
                arrival_rate=args.arrival_rate,
                config=config,
                output_path=args.output,
                audit_mode=args.audit,
                audit_dir=layout["audit_dir"],
                run_index=i + 1,
                num_doctors=args.num_doctors,
                doctor_outage_id=args.doctor_outage,
                outage_start_min=args.outage_start,
                outage_duration_min=args.outage_duration,
                scenario=args.scenario or "manual",
                assignment_strategy=args.assignment_strategy,
                allow_synthetic=args.allow_synthetic,
                burst_size=args.burst_size if args.burst_size is not None else 15,
                burst_start_min=args.burst_start if args.burst_start is not None else 240.0,
                burst_interval_min=args.burst_interval if args.burst_interval is not None else 4.0,
                burst_duration_min=args.burst_duration,
            )
            summaries.append(record)
            all_summaries.append(record)
            mods = record.get("doctors_by_modality", {})
            mods_str = " ".join(f"{k}:{v}" for k, v in sorted(mods.items()))
            print(f"  run {i+1}/{args.n_runs}: "
                  f"k={record.get('num_doctors', '?')} [{mods_str}] | "
                f"SLA_CITO={record['sla_cito']:.3f} "
                f"SLA_plan={record['sla_plan_target']:.3f} "
                f"SLA_max={record['sla_plan_max']:.3f} "
                f"var={record['sigma_w2']:.4f} "
                f"TAT={record['tat_median_min']:.1f}min "
                  f"X={record['throughput_per_hour']:.1f}/h")

        if args.n_runs > 1:
            keys = ["sla_cito", "sla_plan_target", "sla_plan_max",
                    "sigma_w2", "tat_median_min", "throughput_per_hour"]
            print("\nSummary:")
            for k in keys:
                vals = [r[k] for r in summaries]
                mean = sum(vals) / len(vals)
                print(f"  {k}: mean={mean:.4f}")

    # Проверка различимости алгоритмов (для сценариев сравнения)
    distinguish_threshold = float(sim_cfg.get("distinguishability_threshold", 0.01))
    warnings = _warn_if_algorithms_not_distinguishable(all_summaries, threshold=distinguish_threshold)
    for w in warnings:
        print(f"WARNING: {w}")
    if warnings and strict_dist:
        print(
            "ERROR: Distinguishability check failed in strict mode; "
            "final chapter-5 run is not acceptable with current scenario settings."
        )
        raise SystemExit(2)

    csv_path = args.output.replace(".jsonl", ".csv")
    try:
        from simulation.stats import jsonl_to_csv, load_jsonl
        all_records = load_jsonl(args.output)
        jsonl_to_csv(all_records, csv_path)
        print(f"CSV:     {csv_path}")
        _write_ch5_contract_outputs(all_records, args.output, layout["plots_dir"])
    except Exception as exc:
        print(f"CSV export failed: {exc}")

    print(f"Results: {args.output}")


def _write_ch5_contract_outputs(records: list[dict], output_jsonl: str, plots_dir: str) -> None:
    """
    Пишет минимальный набор контрактных файлов главы 5 рядом с output_jsonl.
    Это не заменяет расширенный анализ, но даёт стандартные входы для таблиц.
    """
    from simulation.stats import compare_algorithms, jsonl_to_csv

    base_dir = plots_dir
    os.makedirs(base_dir, exist_ok=True)

    def _save_subset(filename: str, subset: list[dict]) -> None:
        if subset:
            jsonl_to_csv(subset, os.path.join(base_dir, filename))

    def _save_summary(filename: str, subset: list[dict]) -> None:
        if not subset:
            return
        summary = compare_algorithms(subset, group_by="algorithm")
        with open(os.path.join(base_dir, filename), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    baseline = [r for r in records if r.get("scenario") == "baseline"]
    cito_burst = [r for r in records if r.get("scenario") == "cito-burst"]
    load_growth = [r for r in records if r.get("scenario") == "growth20"]
    validation = [r for r in records if r.get("scenario") == "validation"]
    mmc_val = [r for r in records if r.get("scenario") == "mmc-validation"]

    _save_subset("baseline_replications.csv", baseline)
    _save_subset("cito_burst_replications.csv", cito_burst)
    _save_subset("load_growth_replications.csv", load_growth)
    _save_subset("mmc_validation_replications.csv", mmc_val)
    if validation:
        verification_rows = []
        for rec in validation:
            seq = rec.get("assignment_sequence", []) or []
            for idx, item in enumerate(seq, start=1):
                task_id, worker_id, assigned_at_min = item
                verification_rows.append({
                    "scenario": rec.get("scenario"),
                    "algo": rec.get("algorithm"),
                    "replication": rec.get("replication", rec.get("run")),
                    "seed": rec.get("seed"),
                    "order_idx": idx,
                    "task_id": task_id,
                    "assigned_to_worker": worker_id,
                    "assigned_at_min": assigned_at_min,
                })
        if verification_rows:
            v_path = os.path.join(base_dir, "verification_order.csv")
            with open(v_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(verification_rows[0].keys()))
                writer.writeheader()
                writer.writerows(verification_rows)

    # Pairwise-заготовки: одна строка = репликация, пригодно для внешнего pairwise-скрипта.
    _save_subset("baseline_pairwise.csv", baseline)
    _save_subset("cito_burst_pairwise.csv", cito_burst)
    _save_subset("pool_sizing.csv", [r for r in records if r.get("scenario") == "manual"])

    _save_summary("baseline_summary.json", baseline)
    _save_summary("cito_burst_summary.json", cito_burst)
    _save_summary("load_growth_summary.json", load_growth)


if __name__ == "__main__":
    main()
