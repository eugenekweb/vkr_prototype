"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица doctors
    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_doctor_id_hash", sa.String(64), nullable=False),
        sa.Column("specializations", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("productivity_rate", sa.Float(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("current_load", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Таблица tasks
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("modality", sa.String(50), nullable=False),
        sa.Column("urgency_class", sa.String(10), nullable=False),
        sa.Column("complexity", sa.Float(), nullable=False),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_target", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_max", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to"], ["doctors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_tasks_state", "tasks", ["state"])
    op.create_index("ix_tasks_modality", "tasks", ["modality"])
    op.create_index("ix_tasks_arrived_at", "tasks", ["arrived_at"])
    op.create_index("ix_tasks_urgency_class", "tasks", ["urgency_class"])
    op.create_index("ix_tasks_deadline_target", "tasks", ["deadline_target"])

    # Таблица assignments
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_used", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Таблица audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_used", sa.String(20), nullable=True),
        sa.Column("queue_depth", sa.Integer(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_task_id", "audit_log", ["task_id"])
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("assignments")
    op.drop_table("tasks")
    op.drop_table("doctors")
