"""Тесты AuditLogger."""
import json
import os
import tempfile
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.audit_logger import AuditLogger
from data.models import EventType


@pytest.fixture
def tmp_jsonl(tmp_path):
    return str(tmp_path / "test_audit.jsonl")


@pytest.fixture
def logger(tmp_jsonl):
    return AuditLogger(session_factory=None, jsonl_path=tmp_jsonl)


def test_log_event_sync_writes_jsonl(logger, tmp_jsonl):
    """log_event_sync() пишет запись в JSONL-файл."""
    task_id = uuid.uuid4()
    logger.log_event_sync(
        event_type=EventType.RECEIVED,
        task_id=task_id,
        algorithm_used="EDF",
        queue_depth=5,
        payload={"modality": "ECG_REST"},
    )
    with open(tmp_jsonl, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == EventType.RECEIVED
    assert record["task_id"] == str(task_id)


def test_log_appends_only(logger, tmp_jsonl):
    """Журнал только дополняется — каждый вызов добавляет строку."""
    for i in range(5):
        logger.log_event_sync(event_type=EventType.ASSIGNED, queue_depth=i)
    with open(tmp_jsonl, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 5


def test_extract_productivity_correct(tmp_jsonl):
    """extract_productivity() возвращает корректную оценку продуктивности."""
    logger = AuditLogger(session_factory=None, jsonl_path=tmp_jsonl)
    doctor_hash = "d001-hash"
    # Два задания с известными duration_h и complexity
    # μ̂_q = 1 / E[duration_h / complexity]
    # задание 1: duration_h=2, complexity=2 → ratio=1
    # задание 2: duration_h=1, complexity=1 → ratio=1
    # E[ratio] = 1 → μ̂_q = 1.0
    for dur, compl in [(2.0, 2.0), (1.0, 1.0)]:
        logger.log_event_sync(
            event_type=EventType.DONE,
            actor=doctor_hash,
            payload={"duration_h": dur, "complexity": compl},
        )
    mu = logger.extract_productivity(doctor_hash)
    assert mu == pytest.approx(1.0, rel=1e-5)


def test_jsonl_format_correct(logger, tmp_jsonl):
    """Каждая строка — корректный JSON с обязательными полями."""
    logger.log_event_sync(
        event_type=EventType.DONE,
        task_id=uuid.uuid4(),
        payload={"TAT": 95.5, "sla_target_met": True},
    )
    with open(tmp_jsonl, encoding="utf-8") as f:
        record = json.loads(f.readline())
    assert "event_id" in record
    assert "event_type" in record
    assert "timestamp" in record
    assert "payload_json" in record


def test_build_entry_populates_core_fields(logger):
    """_build_entry() заполняет обязательные поля записи."""
    task_id = uuid.uuid4()
    entry = logger._build_entry(
        event_type=EventType.ASSIGNED,
        actor="doctor-1",
        task_id=task_id,
        algorithm_used="EDF",
        queue_depth=3,
        payload={"x": 1},
    )

    assert entry.event_type == EventType.ASSIGNED
    assert entry.task_id == task_id
    assert entry.actor == "doctor-1"
    assert entry.algorithm_used == "EDF"
    assert entry.queue_depth == 3
    assert entry.payload_json == {"x": 1}


def test_flush_with_empty_buffer_is_noop(logger, tmp_jsonl):
    """flush() без буфера не пишет файл и не падает."""
    logger.flush()
    assert not os.path.exists(tmp_jsonl) or os.path.getsize(tmp_jsonl) == 0


def test_flush_handles_write_error(tmp_jsonl, monkeypatch):
    """flush() проглатывает ошибку записи и очищает буфер."""
    logger = AuditLogger(session_factory=None, jsonl_path=tmp_jsonl)
    logger._buffer_lines.append("broken-line\n")

    def fail_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", fail_open)

    logger.flush()
    assert logger._buffer_lines == []


@pytest.mark.asyncio
async def test_log_event_async_uses_session_factory(tmp_path):
    """log_event() пишет и в БД-ветку, и в JSONL."""
    jsonl_path = str(tmp_path / "audit.jsonl")
    logger = AuditLogger(session_factory=None, jsonl_path=jsonl_path)

    session = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)

    factory_cm = MagicMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=factory_cm)
    logger._session_factory = session_factory

    entry = await logger.log_event(
        event_type=EventType.RECEIVED,
        actor="system",
        payload={"modality": "ECG_REST"},
    )

    assert entry.event_type == EventType.RECEIVED
    session.add.assert_called_once()
    logger.flush()
    assert os.path.exists(jsonl_path)


def test_log_event_sync_triggers_immediate_flush(tmp_path):
    """log_event_sync() сразу пишет строку на диск."""
    jsonl_path = str(tmp_path / "audit.jsonl")
    logger = AuditLogger(session_factory=None, jsonl_path=jsonl_path)

    logger.log_event_sync(event_type=EventType.DONE, actor="doctor-1")

    with open(jsonl_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1


def test_extract_arrival_rate_with_iso_and_minutes(tmp_path):
    """extract_arrival_rate() поддерживает ISO-времена и arrived_at_min."""
    jsonl_path = str(tmp_path / "audit.jsonl")
    logger = AuditLogger(session_factory=None, jsonl_path=jsonl_path)

    events = [
        {
            "event_type": EventType.RECEIVED,
            "payload_json": {"arrived_at": "2025-01-01T00:00:00"},
        },
        {
            "event_type": EventType.RECEIVED,
            "payload_json": {"arrived_at_min": 60},
        },
    ]
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    rates = logger.extract_arrival_rate(period_hours=3)
    assert rates == [1, 1, 0]


def test_extract_arrival_rate_missing_file(tmp_path):
    """extract_arrival_rate() без файла возвращает пустой список."""
    logger = AuditLogger(session_factory=None, jsonl_path=str(tmp_path / "missing.jsonl"))
    assert logger.extract_arrival_rate() == []


def test_extract_productivity_missing_file(tmp_path):
    """extract_productivity() без файла возвращает 1.0."""
    logger = AuditLogger(session_factory=None, jsonl_path=str(tmp_path / "missing.jsonl"))
    assert logger.extract_productivity("doctor-x") == 1.0


def test_extract_complexity_distribution(tmp_path):
    """extract_complexity_distribution() собирает статистику по модальности."""
    jsonl_path = str(tmp_path / "audit.jsonl")
    logger = AuditLogger(session_factory=None, jsonl_path=jsonl_path)

    records = [
        {"event_type": EventType.RECEIVED, "payload_json": {"modality": "ECG_REST", "complexity": 1.0}},
        {"event_type": EventType.RECEIVED, "payload_json": {"modality": "ECG_REST", "complexity": 3.0}},
        {"event_type": EventType.RECEIVED, "payload_json": {"modality": "EEG", "complexity": 10.0}},
    ]
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    stats = logger.extract_complexity_distribution("ECG_REST")
    assert stats["count"] == 2
    assert stats["mean"] == pytest.approx(2.0)
    assert stats["variance"] == pytest.approx(1.0)
    assert stats["values"] == [1.0, 3.0]


def test_extract_complexity_distribution_missing_file(tmp_path):
    """extract_complexity_distribution() без файла возвращает пустой словарь."""
    logger = AuditLogger(session_factory=None, jsonl_path=str(tmp_path / "missing.jsonl"))
    assert logger.extract_complexity_distribution("ECG_REST") == {}
