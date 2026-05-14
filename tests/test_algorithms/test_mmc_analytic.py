"""Проверка аналитики M/M/c (Erlang C) для сценария mmc-validation."""
import math

import pytest
import yaml

from simulation.mmc_analytic import erlang_c_wait_metrics


def test_erlang_c_mm1_matches_classic():
    """M/M/1: P_wait = rho, E[Wq] = rho/(mu-lambda) = lambda/(mu(mu-lambda))."""
    lam, mu = 5.0, 10.0
    p_wait, wq_h, rho = erlang_c_wait_metrics(1, lam, mu)
    assert abs(rho - 0.5) < 1e-12
    assert abs(p_wait - 0.5) < 1e-12
    assert abs(wq_h - 0.1) < 1e-12


@pytest.mark.integration
def test_mmc_validation_scenario_smoke():
    """Короткий прогон mmc-validation завершается и даёт конечную аналитику ожидания."""
    from algorithms.base import AlgorithmConfig

    with open("config/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg = dict(cfg)
    sim = dict(cfg.get("simulation", {}))
    sim["warmup_tasks"] = 0
    sim["mmc_validation"] = {"num_servers": 3, "mu_per_hour": 10.0, "warmup_tasks": 0}
    cfg["simulation"] = sim

    from simulation.simulator import Simulator

    algo = dict(cfg.get("algorithm", {}))
    algo["type"] = "FIFO"
    params = AlgorithmConfig.from_dict(algo)
    sim_obj = Simulator(
        algorithm_type="FIFO",
        params=params,
        seed=7,
        config=cfg,
        scenario="mmc-validation",
    )
    r = sim_obj.run_with_rate(2 * 8 * 60.0, 120.0)
    assert r.completed_tasks > 10
    assert math.isfinite(r.mmc_analytic_mean_wait_min)
    assert r.mmc_analytic_mean_wait_min >= 0.0
