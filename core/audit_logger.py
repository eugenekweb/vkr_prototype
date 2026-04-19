"""Журнал событий для операционного и экспериментального контуров."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from data.models import AuditLogEntry, EventType

logger = logging.getLogger(__name__)

_JSONL_PATH = os.getenv("AUDIT_JSONL", "logs/audit.jsonl")


class AuditLogger:
    """Записывает события в PostgreSQL и JSONL-файл."""

    def __init__(
        self,
        session_factory=None,
        jsonl_path: str = _JSONL_PATH,
    ) -> None:
        self._session_factory = session_factory
        self._jsonl_path = jsonl_path
        os.makedirs(
            os.path.dirname(jsonl_path) if os.path.dirname(jsonl_path) else ".",
            exist_ok=True,
        )
        self._buffer_lines: list[str] = []
        self._buffer_max: int = int(os.getenv("AUDIT_BUFFER_MAX", "2000"))

    def _build_entry(
        self,
        event_type: str,
        actor: str = "system",
        task_id: Optional[uuid.UUID] = None,
        algorithm_used: Optional[str] = None,
        queue_depth: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        return AuditLogEntry(
            id=uuid.uuid4(),
            event_type=event_type,
            task_id=task_id,
            actor=actor,
            timestamp=datetime.now(timezone.utc),
            algorithm_used=algorithm_used,
            queue_depth=queue_depth,
            payload_json=payload or {},
        )

    def flush(self) -> None:
        """Сбрасывает буфер JSONL на диск."""
        if not self._buffer_lines:
            return
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write("".join(self._buffer_lines))
        except Exception as exc:
            logger.warning("AuditLogger JSONL flush error: %s", exc)
        finally:
            self._buffer_lines.clear()

    async def log_event(
        self,
        event_type: str,
        actor: str = "system",
        task_id: Optional[uuid.UUID] = None,
        algorithm_used: Optional[str] = None,
        queue_depth: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        """Записывает событие в БД и JSONL."""
        entry = self._build_entry(
            event_type=event_type,
            actor=actor,
            task_id=task_id,
            algorithm_used=algorithm_used,
            queue_depth=queue_depth,
            payload=payload,
        )
        if self._session_factory:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(entry)
        self._write_jsonl(entry)
        return entry

    def log_event_sync(
        self,
        event_type: str,
        actor: str = "system",
        task_id: Optional[uuid.UUID] = None,
        algorithm_used: Optional[str] = None,
        queue_depth: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        """Записывает событие только в JSONL."""
        entry = self._build_entry(
            event_type=event_type,
            actor=actor,
            task_id=task_id,
            algorithm_used=algorithm_used,
            queue_depth=queue_depth,
            payload=payload,
        )
        self._write_jsonl(entry)
        # Синхронный путь используется в тестах и SimPy-контуре, поэтому
        # сохраняем запись на диск сразу, без ожидания заполнения буфера.
        self.flush()
        return entry

    def _write_jsonl(self, entry: AuditLogEntry) -> None:
        """Добавляет запись в буфер JSONL."""
        record = {
            "event_id": str(entry.id),
            "event_type": entry.event_type,
            "timestamp": (
                entry.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            ),
            "task_id": str(entry.task_id) if entry.task_id else None,
            "actor": entry.actor,
            "algorithm_used": entry.algorithm_used,
            "queue_depth": entry.queue_depth,
            "payload_json": entry.payload_json,
        }
        try:
            line = json.dumps(record, ensure_ascii=False) + "\n"
            self._buffer_lines.append(line)
            if len(self._buffer_lines) >= self._buffer_max:
                self.flush()
        except Exception as exc:
            logger.warning("AuditLogger JSONL write error: %s", exc)

    def extract_arrival_rate(self, period_hours: float = 8.0) -> list[float]:
        """Возвращает почасовую интенсивность входящего потока."""
        from datetime import timedelta
        _SIM_BASE = datetime(2025, 1, 1, 0, 0, 0)
        arrivals: list[datetime] = []
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("event_type") == EventType.RECEIVED:
                        payload = rec.get("payload_json") or {}
                        if "arrived_at" in payload:
                            arrivals.append(
                                datetime.fromisoformat(payload["arrived_at"])
                            )
                        elif "arrived_at_min" in payload:
                            arrivals.append(
                                _SIM_BASE
                                + timedelta(
                                    minutes=float(payload["arrived_at_min"])
                                )
                            )
        except FileNotFoundError:
            return []
        if not arrivals:
            return []
        arrivals.sort()
        start = arrivals[0]
        buckets: dict[int, int] = {}
        for t in arrivals:
            hour = int((t - start).total_seconds() // 3600)
            buckets[hour] = buckets.get(hour, 0) + 1
        return [buckets.get(h, 0) for h in range(int(period_hours))]

    def extract_productivity(self, doctor_id_hash: str) -> float:
        """Оценивает производительность врача по событиям DONE."""
        ratios: list[float] = []
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("event_type") != EventType.DONE:
                        continue
                    if rec.get("actor") != doctor_id_hash:
                        continue
                    payload = rec.get("payload_json") or {}
                    duration_h = payload.get("duration_h")
                    complexity = payload.get("complexity")
                    if duration_h and complexity and complexity > 0:
                        ratios.append(duration_h / complexity)
        except FileNotFoundError:
            return 1.0
        if not ratios:
            return 1.0
        return 1.0 / (sum(ratios) / len(ratios))

    def extract_complexity_distribution(self, modality: str) -> dict:
        """Возвращает эмпирическое распределение сложности по модальности."""
        values: list[float] = []
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("event_type") != EventType.RECEIVED:
                        continue
                    payload = rec.get("payload_json") or {}
                    if payload.get("modality") == modality:
                        c = payload.get("complexity")
                        if c:
                            values.append(float(c))
        except FileNotFoundError:
            return {}
        if not values:
            return {}
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return {
            "count": len(values),
            "mean": mean,
            "variance": variance,
            "values": values,
        }
