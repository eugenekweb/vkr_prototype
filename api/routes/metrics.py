"""Роутер метрик."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from api.dependencies import (
    get_metrics_collector,
    get_queue_manager,
    get_session_factory,
)
from api.schemas.metrics import MetricsResponse
from core.metrics_collector import MetricsCollector
from core.queue_manager import QueueManager
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_metrics(
    qm: QueueManager = Depends(get_queue_manager),
    mc: MetricsCollector = Depends(get_metrics_collector),
    sf=Depends(get_session_factory),
):
    """Возвращает текущий снимок метрик."""
    from data.repository import DoctorRepository
    async with sf() as session:
        async with session.begin():
            doctors = await DoctorRepository(session).get_all()
    queue = qm.get_queue_state()
    snap = mc.get_metrics(queue, doctors)
    return MetricsResponse(
        SLA_CITO_target=snap.sla_cito_target,
        SLA_plan_target=snap.sla_plan_target,
        SLA_plan_max=snap.sla_plan_max,
        load_variance=snap.load_variance,
        queue_depth=snap.queue_depth,
        queue_by_modality=snap.queue_by_modality,
        doctors_load=snap.doctors_load,
        timestamp=snap.timestamp,
    )


@router.get("/history")
async def get_metrics_history(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    sf=Depends(get_session_factory),
):
    """Возвращает события за период."""
    from data.repository import AuditRepository
    if not start or not end:
        return {"error": "Укажите start и end"}
    async with sf() as session:
        async with session.begin():
            events = await AuditRepository(session).get_events_by_period(start, end)
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat(),
            "payload": e.payload_json,
        }
        for e in events
    ]


@router.get("/queue")
async def get_queue_metrics(
    qm: QueueManager = Depends(get_queue_manager),
    mc: MetricsCollector = Depends(get_metrics_collector),
):
    """Возвращает сводку очереди по модальностям."""
    queue = qm.get_queue_state()
    by_mod = mc.get_queue_depth_by_modality(queue)
    return {
        "total": len(queue),
        "by_modality": by_mod,
        "queued": sum(1 for t in queue if t.state == "QUEUED"),
        "escalated": sum(1 for t in queue if t.state == "ESCALATED"),
    }
