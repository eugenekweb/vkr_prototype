"""Роутер врачей."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_audit_logger, get_session_factory
from api.schemas.doctor import DoctorAvailabilityRequest, DoctorResponse
from core.audit_logger import AuditLogger
from data.models import EventType

router = APIRouter(prefix="/doctors", tags=["doctors"])


def _make_response(doctor) -> DoctorResponse:
    return DoctorResponse(
        id=doctor.id,
        specializations=doctor.specializations,
        productivity_rate=doctor.productivity_rate,
        is_available=doctor.is_available,
        current_load=doctor.current_load,
        normalized_load=doctor.current_load / doctor.productivity_rate if doctor.productivity_rate else None,
    )


@router.get("", response_model=list[DoctorResponse])
async def list_doctors(sf=Depends(get_session_factory)):
    """GET /doctors — список врачей с текущей нагрузкой."""
    from data.repository import DoctorRepository
    async with sf() as session:
        async with session.begin():
            doctors = await DoctorRepository(session).get_all()
    return [_make_response(d) for d in doctors]


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(doctor_id: uuid.UUID, sf=Depends(get_session_factory)):
    """GET /doctors/{id}."""
    from data.repository import DoctorRepository
    async with sf() as session:
        async with session.begin():
            doctor = await DoctorRepository(session).get_by_id(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Врач не найден")
    return _make_response(doctor)


@router.put("/{doctor_id}/availability", response_model=DoctorResponse)
async def set_availability(
    doctor_id: uuid.UUID,
    body: DoctorAvailabilityRequest,
    al: AuditLogger = Depends(get_audit_logger),
    sf=Depends(get_session_factory),
):
    """PUT /doctors/{id}/availability — обновление avail_q(t)."""
    from data.repository import DoctorRepository
    async with sf() as session:
        async with session.begin():
            repo = DoctorRepository(session)
            doctor = await repo.get_by_id(doctor_id)
            if not doctor:
                raise HTTPException(status_code=404, detail="Врач не найден")
            doctor.is_available = body.is_available
    if not body.is_available:
        await al.log_event(
            event_type=EventType.DOCTOR_UNAVAILABLE,
            actor=str(doctor_id),
            payload={"doctor_id": str(doctor_id), "is_available": False},
        )
    return _make_response(doctor)


@router.get("/{doctor_id}/tasks")
async def get_doctor_tasks(doctor_id: uuid.UUID, sf=Depends(get_session_factory)):
    """GET /doctors/{id}/tasks — текущие задания врача."""
    from data.repository import TaskRepository
    async with sf() as session:
        async with session.begin():
            tasks = await TaskRepository(session).get_tasks_for_doctor(doctor_id)
    return [{"id": str(t.id), "state": t.state, "modality": t.modality} for t in tasks]
