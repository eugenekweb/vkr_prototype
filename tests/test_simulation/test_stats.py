"""Тесты для модуля анализа статистики симуляционных прогонов."""
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from simulation.stats import (
    load_jsonl,
    jsonl_to_csv,
    bootstrap_ci,
    wilcoxon_test,
    compare_algorithms,
    print_comparison_table,
    _normalize_record,
    _REQUIRED_FIELDS,
    _SUMMARY_METRICS,
)


@pytest.mark.unit
@pytest.mark.simulation
def test_normalize_record_legacy_keys():
    """Нормализация legacy-ключей к snake_case."""
    legacy = {
        "SLA_CITO_target": 0.95,
        "SLA_plan_target": 0.90,
        "median_TAT_min": 15.5,
        "load_variance": 2.3,
    }
    normalized = _normalize_record(legacy)
    assert normalized["sla_cito"] == 0.95
    assert normalized["sla_plan_target"] == 0.90
    assert normalized["tat_median_min"] == 15.5
    assert normalized["sigma_w2"] == 2.3


@pytest.mark.unit
@pytest.mark.simulation
def test_normalize_record_preserves_new_keys():
    """Нормализация не перезаписывает новые ключи."""
    record = {
        "sla_cito": 0.95,
        "SLA_CITO_target": 0.85,  # legacy — будет проигнорирован
    }
    normalized = _normalize_record(record)
    # Новые ключи имеют приоритет
    assert normalized["sla_cito"] == 0.95


@pytest.mark.unit
@pytest.mark.simulation
def test_load_jsonl_valid_file(tmp_path):
    """Чтение корректного JSONL-файла."""
    jsonl_file = tmp_path / "results.jsonl"
    records = [
        {"scenario": "baseline", "algorithm": "EDF", "seed": 1, "sla_plan_target": 0.85},
        {"scenario": "baseline", "algorithm": "FIFO", "seed": 2, "sla_plan_target": 0.75},
    ]
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    loaded = load_jsonl(str(jsonl_file))
    assert len(loaded) == 2
    assert loaded[0]["algorithm"] == "EDF"
    assert loaded[1]["algorithm"] == "FIFO"


@pytest.mark.unit
@pytest.mark.simulation
def test_load_jsonl_with_blank_lines(tmp_path):
    """JSONL с пустыми строками — пропускаются."""
    jsonl_file = tmp_path / "results_blank.jsonl"
    with open(jsonl_file, "w", encoding="utf-8") as f:
        f.write('{"algorithm": "EDF", "seed": 1}\n')
        f.write('\n')  # пустая строка
        f.write('{"algorithm": "FIFO", "seed": 2}\n')

    loaded = load_jsonl(str(jsonl_file))
    assert len(loaded) == 2


@pytest.mark.unit
@pytest.mark.simulation
def test_load_jsonl_empty_file(tmp_path):
    """Пустой JSONL-файл."""
    jsonl_file = tmp_path / "empty.jsonl"
    jsonl_file.write_text("")

    loaded = load_jsonl(str(jsonl_file))
    assert len(loaded) == 0


@pytest.mark.unit
@pytest.mark.simulation
def test_jsonl_to_csv_basic(tmp_path):
    """Экспорт JSONL в CSV."""
    records = [
        {
            "scenario": "baseline",
            "algorithm": "EDF",
            "seed": 1,
            "sla_plan_target": 0.85,
            "sigma_w2": 1.2,
        },
        {
            "scenario": "baseline",
            "algorithm": "FIFO",
            "seed": 2,
            "sla_plan_target": 0.75,
            "sigma_w2": 0.9,
        },
    ]
    csv_file = tmp_path / "results.csv"

    jsonl_to_csv(
        records,
        str(csv_file),
        fields=["scenario", "algorithm", "seed", "sla_plan_target", "sigma_w2"],
    )

    assert csv_file.exists()
    content = csv_file.read_text()
    lines = content.strip().split("\n")
    assert len(lines) == 3  # header + 2 records
    assert "scenario,algorithm,seed" in lines[0]


@pytest.mark.unit
@pytest.mark.simulation
def test_jsonl_to_csv_empty_list(tmp_path):
    """CSV экспорт пустого списка — файл не создаётся."""
    csv_file = tmp_path / "empty.csv"
    jsonl_to_csv([], str(csv_file))
    assert not csv_file.exists()


@pytest.mark.unit
@pytest.mark.simulation
def test_jsonl_to_csv_creates_directory(tmp_path):
    """Директория для CSV создаётся автоматически."""
    records = [{"scenario": "baseline", "algorithm": "EDF", "seed": 1}]
    csv_file = tmp_path / "subdir" / "results.csv"

    jsonl_to_csv(records, str(csv_file), fields=["scenario", "algorithm", "seed"])

    assert csv_file.parent.exists()
    assert csv_file.exists()


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_mean_confidence():
    """Bootstrap CI для среднего значения."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0] * 20  # 100 значений
    mean_est, ci_low, ci_high = bootstrap_ci(values, confidence=0.95, n_boot=1000, seed=42)

    # mean_est ~ 3.0
    assert 2.8 < mean_est < 3.2
    # CI должен содержать истинное среднее
    assert ci_low <= mean_est <= ci_high
    # CI должен быть разумного размера (не слишком широкий)
    assert ci_high - ci_low < 1.0


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_custom_stat():
    """Bootstrap CI с пользовательской статистикой (медиана)."""
    import statistics

    values = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
    median_est, ci_low, ci_high = bootstrap_ci(
        values,
        stat_fn=statistics.median,
        confidence=0.95,
        n_boot=500,
        seed=42,
    )

    # медиана ~ 3.0
    assert 2.5 < median_est < 3.5
    assert ci_low <= median_est <= ci_high


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_reproducibility():
    """Bootstrap CI с одинаковым seed даёт одинаковые результаты."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0] * 20

    result1 = bootstrap_ci(values, confidence=0.95, n_boot=500, seed=42)
    result2 = bootstrap_ci(values, confidence=0.95, n_boot=500, seed=42)

    assert result1[0] == result2[0]  # mean_est
    assert result1[1] == result2[1]  # ci_low
    assert result1[2] == result2[2]  # ci_high


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_default_stat_is_mean():
    """Без stat_fn используется среднее."""
    values = [10.0, 20.0, 30.0]
    mean_est, _, _ = bootstrap_ci(values, n_boot=100, seed=42)

    # Должно быть близко к 20.0
    assert abs(mean_est - 20.0) < 1.0


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_single_value():
    """Bootstrap CI для одного значения."""
    values = [5.0] * 100
    mean_est, ci_low, ci_high = bootstrap_ci(values, n_boot=100, seed=42)

    # Должно быть ровно 5.0
    assert mean_est == 5.0
    assert ci_low == 5.0
    assert ci_high == 5.0


@pytest.mark.unit
@pytest.mark.simulation
def test_bootstrap_ci_empty_values():
    """Пустая выборка в bootstrap_ci() возвращает NaN-результат."""
    point, ci_low, ci_high = bootstrap_ci([])
    assert point != point
    assert ci_low != ci_low
    assert ci_high != ci_high


@pytest.mark.unit
@pytest.mark.simulation
def test_required_fields_constant():
    """Проверка наличия обязательных полей."""
    assert "scenario" in _REQUIRED_FIELDS
    assert "algorithm" in _REQUIRED_FIELDS
    assert "seed" in _REQUIRED_FIELDS
    assert "sla_plan_target" in _REQUIRED_FIELDS
    assert len(_REQUIRED_FIELDS) > 5


@pytest.mark.unit
@pytest.mark.simulation
def test_summary_metrics_constant():
    """Проверка метрик для сводки."""
    assert "sla_plan_target" in _SUMMARY_METRICS
    assert "tat_p95_min" in _SUMMARY_METRICS
    assert "throughput_per_hour" in _SUMMARY_METRICS
    assert len(_SUMMARY_METRICS) >= 7


@pytest.mark.unit
@pytest.mark.simulation
def test_normalize_record_extra_fields():
    """Нормализация с дополнительными полями."""
    record = {
        "scenario": "baseline",
        "algorithm": "EDF",
        "sla_plan_target": 0.85,
        "custom_field": "value",
    }
    normalized = _normalize_record(record)
    assert normalized["custom_field"] == "value"
    assert normalized["scenario"] == "baseline"


@pytest.mark.unit
@pytest.mark.simulation
def test_wilcoxon_test_insufficient_data():
    """wilcoxon_test() корректно обрабатывает пустую выборку."""
    u_stat, conclusion = wilcoxon_test([], [1.0, 2.0])
    assert u_stat != u_stat
    assert conclusion == "insufficient data"


@pytest.mark.unit
@pytest.mark.simulation
def test_wilcoxon_test_returns_result_for_equal_samples():
    """wilcoxon_test() возвращает результат на валидных данных."""
    u_stat, conclusion = wilcoxon_test([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert isinstance(u_stat, float)
    assert "p" in conclusion


@pytest.mark.unit
@pytest.mark.simulation
def test_compare_algorithms_groups_and_missing_metrics():
    """compare_algorithms() группирует записи и сохраняет None для пустых метрик."""
    records = [
        {"algorithm": "EDF", "sla_plan_target": 0.9, "sla_cito": 1.0, "tat_p95_min": 10.0},
        {"algorithm": "EDF", "sla_plan_target": 0.8, "sla_cito": 0.9, "tat_p95_min": 12.0},
        {"algorithm": "FIFO", "sla_plan_target": 0.7, "sigma_w2": 1.5},
    ]
    comparison = compare_algorithms(records, metrics=["sla_plan_target", "sla_cito", "sigma_w2"], group_by="algorithm")

    assert set(comparison.keys()) == {"EDF", "FIFO"}
    assert comparison["EDF"]["sla_plan_target"]["n"] == 2
    assert comparison["FIFO"]["sla_cito"]["mean"] is None
    assert comparison["FIFO"]["sigma_w2"]["n"] == 1


@pytest.mark.unit
@pytest.mark.simulation
def test_compare_algorithms_default_metrics():
    """compare_algorithms() использует метрики по умолчанию."""
    records = [
        {"algorithm": "EDF", "sla_plan_target": 0.9, "sla_cito": 1.0},
        {"algorithm": "EDF", "sla_plan_target": 0.8, "sla_cito": 0.9},
    ]
    comparison = compare_algorithms(records)
    assert "EDF" in comparison
    assert "sla_plan_target" in comparison["EDF"]


@pytest.mark.unit
@pytest.mark.simulation
def test_compare_algorithms_group_by_assignment_strategy():
    """compare_algorithms() может группировать по assignment_strategy."""
    records = [
        {"assignment_strategy": "wll", "sla_plan_target": 0.9},
        {"assignment_strategy": "round-robin", "sla_plan_target": 0.8},
    ]
    comparison = compare_algorithms(records, metrics=["sla_plan_target"], group_by="assignment_strategy")

    assert set(comparison.keys()) == {"wll", "round-robin"}


@pytest.mark.unit
@pytest.mark.simulation
def test_print_comparison_table_outputs_values(capsys):
    """print_comparison_table() печатает значения и пустые ячейки."""
    comparison = {
        "EDF": {
            "sla_plan_target": {"mean": 0.91, "ci_lo": 0.88, "ci_hi": 0.94},
            "sla_cito": {"mean": None, "ci_lo": None, "ci_hi": None},
        },
        "FIFO": {
            "sla_plan_target": {"mean": 0.81, "ci_lo": 0.77, "ci_hi": 0.84},
            "sla_cito": {"mean": 0.95, "ci_lo": 0.92, "ci_hi": 0.98},
        },
    }
    print_comparison_table(comparison, metrics=["sla_plan_target", "sla_cito"])
    out = capsys.readouterr().out
    assert "Метрика" in out
    assert "sla_plan_target" in out
    assert "0.9100" in out
    assert "—" in out


@pytest.mark.unit
@pytest.mark.simulation
def test_print_comparison_table_default_metrics(capsys):
    """print_comparison_table() без metrics использует стандартный набор."""
    comparison = {"EDF": {"sla_plan_target": {"mean": 0.91, "ci_lo": 0.88, "ci_hi": 0.94}}}
    print_comparison_table(comparison)
    out = capsys.readouterr().out
    assert "sla_plan_target" in out


@pytest.mark.unit
@pytest.mark.simulation
def test_main_compare_csv_and_wilcoxon(monkeypatch, tmp_path, capsys):
    """main() проходит через csv, compare и wilcoxon ветки."""
    import simulation.stats as stats_mod

    input_path = tmp_path / "input.jsonl"
    input_path.write_text("ignored\n", encoding="utf-8")
    csv_path = tmp_path / "out.csv"

    records = [
        {"algorithm": "EDF", "sla_plan_target": 0.9, "assignment_strategy": "wll"},
        {"algorithm": "EDF", "sla_plan_target": 0.8, "assignment_strategy": "wll"},
        {"algorithm": "FIFO", "sla_plan_target": 0.7, "assignment_strategy": "wll"},
        {"algorithm": "FIFO", "sla_plan_target": 0.6, "assignment_strategy": "wll"},
    ]

    monkeypatch.setattr(stats_mod, "load_jsonl", lambda path: records)
    csv_calls = []
    monkeypatch.setattr(stats_mod, "jsonl_to_csv", lambda recs, path: csv_calls.append((recs, path)))
    monkeypatch.setattr(stats_mod, "compare_algorithms", lambda recs, group_by="algorithm": {"EDF": {}, "FIFO": {}})
    monkeypatch.setattr(stats_mod, "print_comparison_table", lambda comparison, metrics=None: print("TABLE"))
    monkeypatch.setattr(stats_mod, "wilcoxon_test", lambda x, y: (1.0, "p < 0.05 (значимо)"))
    monkeypatch.setattr(stats_mod, "bootstrap_ci", lambda values, seed=0: (0.75, 0.70, 0.80))
    monkeypatch.setattr(
        stats_mod.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(
            input=str(input_path),
            csv=str(csv_path),
            compare=True,
            group_by="algorithm",
            wilcoxon=["EDF", "FIFO"],
            metric="sla_plan_target",
            seed=0,
        ),
    )

    stats_mod.main()
    out = capsys.readouterr().out
    assert "Загружено 4 записей" in out
    assert "CSV сохранён" in out
    assert "TABLE" in out
    assert "Критерий Вилкоксона" in out
    assert csv_calls and csv_calls[0][1] == str(csv_path)


@pytest.mark.unit
@pytest.mark.simulation
def test_main_wilcoxon_no_data(monkeypatch, tmp_path, capsys):
    """main() печатает сообщение об отсутствии данных для wilcoxon."""
    import simulation.stats as stats_mod

    input_path = tmp_path / "input.jsonl"
    input_path.write_text("ignored\n", encoding="utf-8")

    monkeypatch.setattr(
        stats_mod,
        "load_jsonl",
        lambda path: [
            {"algorithm": "EDF", "sla_plan_target": 0.9},
            {"algorithm": "FIFO"},
        ],
    )
    monkeypatch.setattr(stats_mod.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(
        input=str(input_path),
        csv=None,
        compare=False,
        group_by="algorithm",
        wilcoxon=["EDF", "FIFO"],
        metric="sla_plan_target",
        seed=0,
    ))

    stats_mod.main()
    out = capsys.readouterr().out
    assert "Нет данных для EDF или FIFO" in out


@pytest.mark.unit
@pytest.mark.simulation
def test_main_without_wilcoxon(monkeypatch, tmp_path, capsys):
    """main() корректно отрабатывает без compare/csv/wilcoxon веток."""
    import simulation.stats as stats_mod

    input_path = tmp_path / "input.jsonl"
    input_path.write_text("ignored\n", encoding="utf-8")
    monkeypatch.setattr(stats_mod, "load_jsonl", lambda path: [])
    monkeypatch.setattr(stats_mod.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(
        input=str(input_path),
        csv=None,
        compare=False,
        group_by="algorithm",
        wilcoxon=None,
        metric="sla_plan_target",
        seed=0,
    ))

    stats_mod.main()
    out = capsys.readouterr().out
    assert "Загружено 0 записей" in out
