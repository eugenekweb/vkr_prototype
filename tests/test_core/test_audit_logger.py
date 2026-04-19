"""Тесты AuditLogger."""
import json
import os
import tempfile
import uuid
from datetime import datetime

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
