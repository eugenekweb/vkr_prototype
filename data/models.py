"""ORM-модели домена задач, врачей и событий."""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TaskState(str, enum.Enum):
    """Состояния задания."""
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    ESCALATED = "ESCALATED"


class UrgencyClass(str, enum.Enum):
    """Класс срочности задания."""
    CITO = "CITO"
    PLAN = "план"


class Modality(str, enum.Enum):
    """Поддерживаемые модальности."""
    ECG_REST = "ECG_REST"
    HOLTER = "HOLTER"
    SMAD = "SMAD"
    ECHO_KG = "ECHO_KG"
    EEG = "EEG"
    ENMG = "ENMG"
    OTHER = "OTHER"


class EventType(str, enum.Enum):
    """Типы событий журнала."""
    RECEIVED = "RECEIVED"
    ASSIGNED = "ASSIGNED"
    INPROGRESS = "INPROGRESS"
    DONE = "DONE"
    SLA_WARNING = "SLA_WARNING"
    SLA_VIOLATION = "SLA_VIOLATION"
    CITO_ESCALATED = "CITO_ESCALATED"
    DOCTOR_UNAVAILABLE = "DOCTOR_UNAVAILABLE"


class Task(Base):
    """Сущность задания."""
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    urgency_class: Mapped[str] = mapped_column(String(10), nullable=False)
    complexity: Mapped[float] = mapped_column(Float, nullable=False)

    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_target: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_max: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    state: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskState.QUEUED)

    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLogEntry"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tasks_state", "state"),
        Index("ix_tasks_modality", "modality"),
        Index("ix_tasks_arrived_at", "arrived_at"),
        Index("ix_tasks_urgency_class", "urgency_class"),
        Index("ix_tasks_deadline_target", "deadline_target"),
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} modality={self.modality} state={self.state}>"


class Doctor(Base):
    """Сущность врача."""
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_doctor_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    specializations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    productivity_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_load: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="doctor")

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} load={self.current_load:.2f}>"


class Assignment(Base):
    """История назначений задач врачам."""
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    algorithm_used: Mapped[str] = mapped_column(String(20), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="assignments")
    doctor: Mapped["Doctor"] = relationship(back_populates="assignments")

    def __repr__(self) -> str:
        return f"<Assignment task={self.task_id} doctor={self.doctor_id} algo={self.algorithm_used}>"


class AuditLogEntry(Base):
    """Событие журнала действий и состояния системы."""
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    algorithm_used: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    queue_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    task: Mapped[Optional["Task"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_log_event_type", "event_type"),
        Index("ix_audit_log_task_id", "task_id"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<AuditLogEntry event={self.event_type} task={self.task_id} ts={self.timestamp}>"
