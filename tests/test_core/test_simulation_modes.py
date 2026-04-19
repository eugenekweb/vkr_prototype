"""Проверка выбора режимов симуляции."""

from simulation.runner import _apply_simulation_mode, _load_config


def test_operational_mode_disables_warmup():
    cfg = _load_config("config/config.yaml")
    resolved, mode = _apply_simulation_mode(cfg, "operational")

    sim_cfg = resolved["simulation"]
    assert mode == "operational"
    assert sim_cfg["mode"] == "operational"
    assert sim_cfg["warmup_tasks"] == 0
    assert sim_cfg["warmup_time_min"] == 0.0
    assert sim_cfg["strict_distinguishability"] is False


def test_evaluation_mode_keeps_warmup_profile():
    cfg = _load_config("config/config.yaml")
    resolved, mode = _apply_simulation_mode(cfg, "evaluation")

    sim_cfg = resolved["simulation"]
    assert mode == "evaluation"
    assert sim_cfg["mode"] == "evaluation"
    assert sim_cfg["warmup_tasks"] == 500
    assert sim_cfg["warmup_time_min"] == 0.0
