"""FastAPI приложение операционного контура."""
from __future__ import annotations

import logging
import os

import yaml
from algorithms.base import AlgorithmConfig
from algorithms.factory import PrioritizerFactory
from api.routes import config, doctors, metrics, tasks
from core.assignment_engine import AssignmentEngine
from core.audit_logger import AuditLogger
from core.metrics_collector import MetricsCollector
from core.queue_manager import QueueManager
from core.scheduler import Scheduler
from data.database import AsyncSessionFactory, get_engine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_config(path: str = "config/config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


app = FastAPI(
    title="TMS — Прототип СУЗ ЦДО",
    description=(
        "Система управления заданиями центра дистанционных описаний. "
        "Два контура: операционный (FastAPI+PostgreSQL) и экспериментальный (SimPy). "
        "Пять алгоритмов приоритизации: FIFO, PQ, Aging, EDF, Hybrid."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(doctors.router)
app.include_router(metrics.router)
app.include_router(config.router)


@app.on_event("startup")
async def startup() -> None:
    """Инициализирует базу, справочники и фоновые компоненты."""
    cfg = _load_config()
    algo_cfg = cfg.get("algorithm", {})
    sla_cfg = cfg.get("sla", {})

    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig
        alembic_cfg = AlembicConfig("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied")
    except Exception as exc:
        logger.warning("Alembic migration skipped: %s", exc)
        from data.models import Base
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created via metadata.create_all")

    async with AsyncSessionFactory() as session:
        async with session.begin():
            from data.seed import seed_doctors
            await seed_doctors(session)

    params = AlgorithmConfig.from_dict(algo_cfg)
    prioritizer = PrioritizerFactory.create(params.type, params)
    assignment_engine = AssignmentEngine()
    queue_manager = QueueManager(prioritizer, assignment_engine, params)

    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                from data.repository import TaskRepository
                pending = await TaskRepository(session).get_queue()
                for t in pending:
                    queue_manager.enqueue(t, force_queued=False)
        logger.info("Queue restored: %d tasks from DB", len(pending))
    except Exception as exc:
        logger.warning("Queue restore failed: %s", exc)
    metrics_collector = MetricsCollector(
        target_hours=sla_cfg.get("target_hours", 2.0),
        max_hours=sla_cfg.get("max_hours", 24.0),
        warning_threshold=sla_cfg.get("warning_threshold", 0.5),
        cito_assign_epsilon_sec=sla_cfg.get("cito_assign_epsilon_sec", 5.0),
    )
    audit_logger = AuditLogger(
        session_factory=AsyncSessionFactory,
        jsonl_path=cfg.get("logging", {}).get("json_log_file", "logs/audit.jsonl"),
    )
    scheduler = Scheduler(
        queue_manager=queue_manager,
        assignment_engine=assignment_engine,
        metrics_collector=metrics_collector,
        audit_logger=audit_logger,
        session_factory=AsyncSessionFactory,
    )

    app.state.queue_manager = queue_manager
    app.state.assignment_engine = assignment_engine
    app.state.metrics_collector = metrics_collector
    app.state.audit_logger = audit_logger
    app.state.scheduler = scheduler
    app.state.sla_config = sla_cfg

    await scheduler.start()
    logger.info("TMS started. Algorithm: %s", params.type)


@app.on_event("shutdown")
async def shutdown() -> None:
    if hasattr(app.state, "scheduler"):
        await app.state.scheduler.stop()
    await get_engine().dispose()


@app.get("/health")
async def health():
    """GET /health — проверка работоспособности."""
    algo = "unknown"
    if hasattr(app.state, "queue_manager"):
        algo = app.state.queue_manager.get_current_algorithm()
    return {"status": "ok", "algorithm": algo, "mode": "operational"}
