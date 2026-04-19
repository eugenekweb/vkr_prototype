"""Эндпоинты для управления заданиями."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.dependencies import (
    get_audit_logger,
    get_metrics_collector,
    get_queue_manager,
    get_session_factory,
    get_sla_config,
)
from api.schemas.task import (
    AuditEventResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskStatusUpdateRequest,
)
from core.audit_logger import AuditLogger
from core.metrics_collector import MetricsCollector
from core.queue_manager import QueueManager
from data.models import EventType, Task, TaskState
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _make_task_response(task: Task, metrics: Optional[MetricsCollector] = None) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        external_id=task.external_id,
        modality=task.modality,
        urgency_class=task.urgency_class,
        complexity=task.complexity,
        arrived_at=task.arrived_at,
        deadline_target=task.deadline_target,
        deadline_max=task.deadline_max,
        state=task.state,
        assigned_to=task.assigned_to,
        started_at=task.started_at,
        done_at=task.done_at,
        escalated_at=task.escalated_at,
        estimated_tat_h=estimated_tat,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(
    body: TaskCreateRequest,
    qm: QueueManager = Depends(get_queue_manager),
    al: AuditLogger = Depends(get_audit_logger),
    sf=Depends(get_session_factory),
    sla_cfg: dict = Depends(get_sla_config),
):
    """Создаёт новое задание или возвращает существующее по external_id."""
    from data.repository import TaskRepository

    target_hours = sla_cfg.get("target_hours", 2.0)
    max_hours = sla_cfg.get("max_hours", 24.0)
    now = datetime.now(timezone.utc)
    async with sf() as session:
        async with session.begin():
            repo = TaskRepository(session)
            existing = await repo.get_by_external_id(body.external_id)
            if existing:
                return _make_task_response(existing)

            deadline_target = now + timedelta(hours=target_hours)
            deadline_max = now + timedelta(hours=max_hours)

            task = Task(
                id=uuid.uuid4(),
                external_id=body.external_id,
                modality=body.modality,
                urgency_class=body.urgency_class,
                complexity=body.complexity,
                arrived_at=now,
                deadline_target=deadline_target,
                deadline_max=deadline_max,
                state=TaskState.QUEUED,
                version=0,
            )
            await repo.create(task)

    qm.enqueue(task)

    await al.log_event(
        event_type=EventType.RECEIVED,
        task_id=task.id,
        queue_depth=len(qm.get_queue_state()),
        payload={
            "modality": task.modality,
            "urgency_class": task.urgency_class,
            "arrived_at": task.arrived_at.isoformat(),
            "deadline_target": deadline_target.isoformat(),
            "deadline_max": deadline_max.isoformat(),
            "complexity": task.complexity,
        },
    )
    return _make_task_response(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    state: Optional[str] = Query(None),
    modality: Optional[str] = Query(None),
    urgency_class: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    sf=Depends(get_session_factory),
):
    """Возвращает список заданий с фильтрами."""
    from data.repository import TaskRepository
    async with sf() as session:
        async with session.begin():
            repo = TaskRepository(session)
            tasks = await repo.list_tasks(
                state=state, modality=modality, urgency_class=urgency_class,
                limit=limit, offset=offset,
            )
    return [_make_task_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    mc: MetricsCollector = Depends(get_metrics_collector),
    qm: QueueManager = Depends(get_queue_manager),
    sf=Depends(get_session_factory),
):
    """Возвращает задание и оценку TAT для очередных состояний."""
    from data.repository import DoctorRepository, TaskRepository
    async with sf() as session:
        async with session.begin():
            task = await TaskRepository(session).get_by_id(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Задание не найдено")
            doctors = await DoctorRepository(session).get_all()

    queue = qm.get_queue_state()
    resp = _make_task_response(task)
    if task.state in (TaskState.QUEUED, TaskState.ESCALATED):
        resp.estimated_tat_h = mc.estimate_tat(task, queue, doctors)
    return resp


@router.put("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: uuid.UUID,
    body: TaskStatusUpdateRequest,
    qm: QueueManager = Depends(get_queue_manager),
    al: AuditLogger = Depends(get_audit_logger),
    mc: MetricsCollector = Depends(get_metrics_collector),
    sf=Depends(get_session_factory),
    sla_cfg: dict = Depends(get_sla_config),
):
    """Изменяет состояние задания."""
    from data.repository import DoctorRepository, TaskRepository

    # I9: SLA-параметры из app.state, не хардкод
    target_hours = sla_cfg.get("target_hours", 2.0)
    max_hours = sla_cfg.get("max_hours", 24.0)
    now = datetime.now(timezone.utc)
    async with sf() as session:
        async with session.begin():
            task_repo = TaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Задание не найдено")

            if body.state == TaskState.IN_PROGRESS:
                task.state = TaskState.IN_PROGRESS
                task.started_at = now
                task.version += 1
                await al.log_event(
                    event_type=EventType.INPROGRESS,
                    task_id=task.id,
                    actor=str(body.doctor_id) if body.doctor_id else "system",
                    payload={"started_at": now.isoformat()},
                )

            elif body.state == TaskState.DONE:
                if not task.started_at:
                    task.started_at = now
                task.state = TaskState.DONE
                task.done_at = now
                task.version += 1
                tat_min = (now - task.arrived_at).total_seconds() / 60.0
                sla_t = tat_min <= target_hours * 60
                sla_m = tat_min <= max_hours * 60
                mc.record_completed(task)
                await al.log_event(
                    event_type=EventType.DONE,
                    task_id=task.id,
                    actor=str(body.doctor_id) if body.doctor_id else "system",
                    payload={
                        "done_at": now.isoformat(),
                        "TAT": round(tat_min, 2),
                        "sla_target_met": sla_t,
                        "sla_max_met": sla_m,
                    },
                )
                # C2: уменьшаем нагрузку по task.assigned_to, не по body.doctor_id
                # body.doctor_id используется только для аудита/валидации
                if task.assigned_to:
                    doc_repo = DoctorRepository(session)
                    await doc_repo.update_load(task.assigned_to, -task.complexity)
                    db_doc = await doc_repo.get_by_id(task.assigned_to)
                    if db_doc:
                        projected_load = max(0.0, db_doc.current_load - task.complexity)
                        if projected_load <= 1e-9:
                            await doc_repo.set_availability(task.assigned_to, True)
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Недопустимое состояние: {body.state}",
                )

    return _make_task_response(task)


@router.post("/{task_id}/escalate", response_model=TaskResponse)
async def escalate_task(
    task_id: uuid.UUID,
    qm: QueueManager = Depends(get_queue_manager),
    al: AuditLogger = Depends(get_audit_logger),
    sf=Depends(get_session_factory),
):
    """Эскалирует задание вручную."""
    from data.repository import TaskRepository
    now = datetime.now(timezone.utc)
    task = qm.escalate(task_id, now)
    from_queue = task is not None
    if task is None:
        async with sf() as session:
            async with session.begin():
                task = await TaskRepository(session).get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")
    async with sf() as session:
        async with session.begin():
            repo = TaskRepository(session)
            await repo.update_state(
                task_id,
                new_state="ESCALATED",
                version=(task.version - 1) if from_queue else task.version,
                escalated_at=now,
            )
    await al.log_event(
        event_type=EventType.CITO_ESCALATED,
        task_id=task_id,
        payload={"triggered_at": now.isoformat(), "manual": True},
    )
    return _make_task_response(task)


@router.get("/{task_id}/history", response_model=list[AuditEventResponse])
async def get_task_history(
    task_id: uuid.UUID,
    sf=Depends(get_session_factory),
):
    """GET /tasks/{id}/history — события из AuditLogEntry."""
    from data.repository import AuditRepository
    async with sf() as session:
        async with session.begin():
            events = await AuditRepository(session).get_events_by_task(task_id)
    return [
        AuditEventResponse(
            id=e.id,
            event_type=e.event_type,
            task_id=e.task_id,
            actor=e.actor,
            timestamp=e.timestamp,
            algorithm_used=e.algorithm_used,
            queue_depth=e.queue_depth,
            payload_json=e.payload_json,
        )
        for e in events
    ]
