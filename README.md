# TMS - прототип СУЗ центра дистанционных описаний

Проект содержит два независимых контура:

- операционный (FastAPI + PostgreSQL);
- экспериментальный (SimPy batch) для воспроизводимых сравнений алгоритмов.

## Операционный контур

Запуск API:

```bash
docker-compose up db tms-api
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
```

## Экспериментальный контур

Запуск через runner:

```bash
python -m simulation.runner \
  --algorithm EDF \
  --scenario-preset baseline_ch5 \
  --days 0.2 \
  --seed 42 \
  --n-runs 1 \
  --audit none \
  --output results/ch5/smoke/baseline_edf.jsonl
```

Канонические preset-ы из config/config.yaml:

- baseline_ch5
- growth20_ch5
- cito_burst_ch5
- validation_mmc

Допустимы алиасы имени preset без подчеркиваний (например, baselineCH5), но в документации используется baseline_ch5.

## Важное поведение runner

- По умолчанию выходной JSONL очищается перед запуском.
- Для дозаписи используйте --append-output.
- --output трактуется как имя summary-файла в batch-каталоге.

Пример:

- при --output results/ch5/d_sweep/d10_baseline.jsonl фактический summary-файл будет записан в results/ch5/d_sweep/summary/d10_baseline.jsonl.

Это штатное поведение layout-резолвера.

## Режимы симуляции

В config/config.yaml определены два режима:

- evaluation - режим сравнительных экспериментов (warmup включен);
- operational - режим операционной имитации (warmup отключен).

Выбор режима через CLI:

```bash
python -m simulation.runner \
  --mode operational \
  --days 1 \
  --n-runs 30 \
  --num-doctors 2 \
  --arrival-rate 300 \
  --audit none \
  --output results/operational/run.jsonl
```

## Алгоритмы

Поддерживаются алгоритмы:

- FIFO
- PQ
- AGING
- EDF
- HYBRID

## Тестирование

Проект содержит **215 unit и интеграционных тестов** с покрытием **68.52%** критических модулей.

```bash
# Запуск всех тестов
python -m pytest tests/ -v

# По компонентам
python -m pytest tests/test_algorithms -v    # 55 тестов алгоритмов
python -m pytest tests/test_core -v           # 70 тестов ядра
python -m pytest tests/test_simulation -v     # 48 тестов симуляции

# С покрытием
python -m pytest tests/ --cov=. --cov-report=html
```

## Быстрый старт разработки

```bash
# 1) Конфигурация
cp .env.example .env
cp config/config.yaml config/config.local.yaml

# Примечание: по умолчанию приложение читает `config/config.yaml`.
# Файл `config.local.yaml` не загружается автоматически — используйте
# опцию `--config path/to/config.yaml` при запуске runner или редактируйте
# `config/config.yaml` напрямую.

# 2) Запуск сервисов
docker-compose up --build

# 3) Создание задания
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"external_id":"mis-001","modality":"ECG_REST","urgency_class":"план","complexity":1.0}'

# 4) Метрики
curl http://localhost:8000/metrics
```

## Минимальные проверки

```bash
python -m pytest tests/test_algorithms -q
python -m pytest tests/test_core -q
python -m pytest tests/test_api -q

python -m simulation.runner \
  --algorithm all \
  --scenario-preset baseline_ch5 \
  --days 0.2 \
  --n-runs 1 \
  --audit none \
  --no-strict-distinguishability \
  --output results/ch5/smoke/baseline_all.jsonl
```

## Структура проекта

```text
tms/
|- api/          FastAPI: роутеры и схемы
|- core/         очередь, назначение, метрики, аудит
|- algorithms/   интерфейс и реализации приоритизации
|- simulation/   SimPy-контур и batch-runner
|- data/         модели, репозитории, миграции
|- tests/        автотесты
|- config/       конфигурация
|- docs/         эксплуатационная документация
`- results/      артефакты прогонов
```
