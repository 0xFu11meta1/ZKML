"""add status indexes and check constraints

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-11

Adds:
- Index on proof_jobs.status for frequent status filtering
- Index on circuits.proof_type for proof-type filtered listings
- Index on circuit_partitions.status for partition sweeps (aggregation, health)
- Check constraint on api_keys.daily_limit > 0
- Index on audit_logs.created_at for date-range filtered exports
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Proof job status is the most common filter in listing/polling queries
    op.create_index(
        "ix_proof_jobs_status",
        "proof_jobs",
        ["status"],
    )

    # Circuit browsing frequently filters by proof system type
    op.create_index(
        "ix_circuits_proof_type",
        "circuits",
        ["proof_type"],
    )

    # Partition sweeps: aggregation task and prover_health both query by status
    op.create_index(
        "ix_circuit_partitions_status",
        "circuit_partitions",
        ["status"],
    )

    # Audit log exports with date-range filtering
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )

    # Ensure daily_limit is always positive
    op.create_check_constraint(
        "ck_api_keys_daily_limit_positive",
        "api_keys",
        sa.column("daily_limit") > 0,
    )


def downgrade() -> None:
    op.drop_constraint("ck_api_keys_daily_limit_positive", "api_keys", type_="check")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_circuit_partitions_status", table_name="circuit_partitions")
    op.drop_index("ix_circuits_proof_type", table_name="circuits")
    op.drop_index("ix_proof_jobs_status", table_name="proof_jobs")
