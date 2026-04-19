"""
FastAPI-зависимости: доступ к компонентам ядра.
Компоненты создаются один раз при старте и хранятся в app.state.
"""
from __future__ import annotations

from fastapi import Request

from core.assignment_engine import AssignmentEngine
from core.audit_logger import AuditLogger
from core.metrics_collector import MetricsCollector
from core.queue_manager import QueueManager
from core.scheduler import Scheduler
from data.database import AsyncSessionFactory


def get_queue_manager(request: Request) -> QueueManager:
    return request.app.state.queue_manager


def get_assignment_engine(request: Request) -> AssignmentEngine:
    return request.app.state.assignment_engine


def get_metrics_collector(request: Request) -> MetricsCollector:
    return request.app.state.metrics_collector


def get_audit_logger(request: Request) -> AuditLogger:
    return request.app.state.audit_logger


def get_scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler


def get_session_factory(request: Request):
    return AsyncSessionFactory


def get_sla_config(request: Request) -> dict:
    """SLA-параметры из app.state (I9): единый источник для routes."""
    return getattr(
        request.app.state,
        "sla_config",
        {"target_hours": 2.0, "max_hours": 24.0},
    )
