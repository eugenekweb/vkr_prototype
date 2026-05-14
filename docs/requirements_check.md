# Проверка требований проекта

Документ фиксирует проверяемые требования и точки в коде, где они реализованы.

## Функциональные требования

| ID   | Критерий                                            | Реализация                                  | Статус |
| ---- | --------------------------------------------------- | ------------------------------------------- | ------ |
| ФТ-1 | Создание задания с дедлайнами target/max            | api/routes/tasks.py                         | OK     |
| ФТ-2 | Task-first диспетчеризация в единой очереди         | core/queue_manager.py                       | OK     |
| ФТ-3 | Горячая смена алгоритма без рестарта                | api/routes/config.py, core/queue_manager.py | OK     |
| ФТ-4 | Назначение только совместимым по модальности врачам | core/assignment_engine.py                   | OK     |
| ФТ-5 | Корректная обработка CITO в цикле диспетчеризации   | core/queue_manager.py                       | OK     |
| ФТ-6 | SLA_WARNING и SLA_VIOLATION по порогам SLA          | core/metrics_collector.py                   | OK     |
| ФТ-7 | Выдача метрик через API                             | api/routes/metrics.py                       | OK     |
| ФТ-8 | Запись событий в БД и JSONL аудит                   | core/audit_logger.py                        | OK     |

## Нефункциональные требования

| ID    | Критерий                                            | Реализация                                        | Статус |
| ----- | --------------------------------------------------- | ------------------------------------------------- | ------ |
| НФТ-1 | Нагрузочный прогон доступен через simulation.runner | simulation/runner.py                              | OK     |
| НФТ-3 | Атомарная замена алгоритма                          | core/queue_manager.py                             | OK     |
| НФТ-4 | Обезличивание внешних идентификаторов врачей        | data/seed.py                                      | OK     |
| НФТ-6 | Append-only аудит                                   | core/audit_logger.py, data/repository.py          | OK     |
| НФТ-7 | Воспроизводимость при фиксированном seed            | simulation/simulator.py, simulation/generators.py | OK     |

## Архитектурные инварианты

| Инвариант                                            | Реализация                                         |
| ---------------------------------------------------- | -------------------------------------------------- |
| Единый интерфейс приоритизации                       | algorithms/base.py                                 |
| Одинаковые алгоритмы в API и SimPy-контуре           | algorithms/\*, simulation/simulator.py             |
| Исключение escalated задач из стандартной сортировки | core/queue_manager.py                              |
| Дисперсия нагрузки считается по завершенным заданиям | simulation/simulator.py, core/metrics_collector.py |

## Тестовое покрытие требований

| Требование                               | Тесты                                         | Покрытие |
| ---------------------------------------- | --------------------------------------------- | -------- |
| ФТ-1...ФТ-8 (функциональные)             | tests/test_api/, tests/test_core/             | 88–100%  |
| НФТ-1, НФТ-3...НФТ-7                     | tests/test_simulation/, tests/test_core/      | 76–100%  |
| Алгоритмы (FIFO, PQ, AGING, EDF, HYBRID) | tests/test_algorithms/                        | 93–100%  |
| Воспроизводимость (seed)                 | tests/test_algorithms/test_reproducibility.py | 100%     |

## Команды проверки

```bash
# Тесты
python -m pytest tests/test_algorithms -q
python -m pytest tests/test_core -q
python -m pytest tests/test_api -q

# Проверка воспроизводимости
python -m pytest tests/test_algorithms/test_reproducibility.py -q
python -m pytest tests/test_core/test_random_usage.py -q

# Smoke-прогон baseline
python -m simulation.runner \
  --algorithm all \
  --scenario-preset baseline_ch5 \
  --days 0.2 \
  --n-runs 1 \
  --audit none \
  --no-strict-distinguishability \
  --output results/ch5/smoke/baseline_all.jsonl

# Строгая проверка различимости
python -m simulation.runner \
  --algorithm all \
  --scenario-preset baseline_ch5 \
  --days 0.2 \
  --n-runs 1 \
  --audit none \
  --strict-distinguishability \
  --output results/ch5/smoke/baseline_strict.jsonl
```
