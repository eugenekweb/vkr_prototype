# Руководство по экспериментальному контуру (SimPy)

## Назначение

Экспериментальный контур выполняет batch-прогоны и формирует воспроизводимые метрики по алгоритмам FIFO, PQ, AGING, EDF и HYBRID.

## Базовый запуск

```bash
python -m simulation.runner \
  --algorithm EDF \
  --scenario-preset baseline_ch5 \
  --days 0.2 \
  --n-runs 1 \
  --seed 42 \
  --audit none \
  --no-strict-distinguishability \
  --output results/ch5/smoke/baseline_edf.jsonl
```

## Preset-ы

Используются preset-ы из config/config.yaml:

- baseline_ch5
- growth20_ch5
- cito_burst_ch5
- validation_mmc

Runner принимает алиасы имен preset без разделителей, но каноническая форма в документации: snake_case.

## Поведение output

Runner всегда пишет summary-файл в подпапку summary выбранного batch-каталога.

Пример:

- аргумент: --output results/ch5/d_sweep/d10_baseline.jsonl
- фактический summary: results/ch5/d_sweep/summary/d10_baseline.jsonl

По умолчанию целевой summary-файл очищается перед запуском.
Для дозаписи требуется флаг --append-output.

## Режимы

- evaluation: режим сравнительных экспериментов;
- operational: режим операционной имитации.

Выбор режима:

```bash
python -m simulation.runner \
  --mode evaluation \
  --algorithm all \
  --scenario-preset baseline_ch5 \
  --n-runs 1 \
  --audit none \
  --output results/ch5/smoke/baseline_all.jsonl
```

## Ключевые флаги

| Флаг                           | Назначение                            |
| ------------------------------ | ------------------------------------- |
| --algorithm                    | FIFO, PQ, AGING, EDF, HYBRID, all     |
| --scenario-preset              | выбор канонического сценария          |
| --days                         | горизонт моделирования в рабочих днях |
| --n-runs                       | число репликаций                      |
| --seed                         | базовый seed                          |
| --mode                         | evaluation или operational            |
| --audit                        | none, sample, full                    |
| --strict-distinguishability    | строгий контроль различимости         |
| --no-strict-distinguishability | отключение strict-проверки            |
| --num-doctors                  | переопределение размера пула          |
| --arrival-rate                 | явное переопределение lambda          |
| --append-output                | дозапись в существующий summary       |

## Формат summary JSONL

Основные поля записи:

- algorithm
- scenario
- replication
- seed
- arrival_rate
- num_doctors
- doctor_source
- sla_cito
- sla_plan_target
- sla_plan_max
- sigma_w2
- rho_avg
- rho_normalized
- tat_median_min
- tat_p95_min
- throughput_per_hour
- completed_tasks

## Проверки

```bash
python -m pytest tests/test_algorithms -q
python -m pytest tests/test_core/test_random_usage.py -q
python -m pytest tests/test_core/test_critical_paths.py -q
```

## Примечание по SLA_WARNING

В реализации событие `SLA_WARNING` формируется внутри `MetricsCollector` при предиктивной проверке (elapsed + estimated TAT). Однако в экспериментальном (SimPy) контуре эта проверка не вызывается для формирования итоговых summary-метрик, поэтому предупреждения `SLA_WARNING` не влияют на сравнительный анализ алгоритмов в главе 5 (они остаются доступными в audit‑логе для детального расследования, но не используются при расчёте агрегированных показателей).

## D-sweep D2-D12

Запуск новых D-прогонов выполняется отдельными файлами dN_baseline.jsonl.

Сборка сводных таблиц:

```bash
python scripts/collect_ch5_results.py --rebuild
```

Результат:

- results/ch5/final_series/summary/final_table_d2_d12_pooled.csv
- results/ch5/final_series/summary/final_table_d2_d12_by_algo.csv
