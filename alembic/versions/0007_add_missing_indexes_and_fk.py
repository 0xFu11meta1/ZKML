"""add missing indexes and foreign key constraints

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-13

Adds:
- Index on circuit_partitions.assigned_prover for dispatcher filtering
- Composite index on (circuit_id, proof_type) for filtered proof queries
- Foreign key on circuits.org_id -> organizations.id
- Index on proof_jobs.requester_hotkey + status for per-user job lookups
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Proof dispatch frequently filters partitions by assigned prover
    op.create_index(
        "ix_circuit_partitions_assigned_prover",
        "circuit_partitions",
        ["assigned_prover"],
    )

    # Proof listings often filter by (circuit_id, proof_type)
    op.create_index(
        "ix_proofs_circuit_proof_type",
        "proofs",
        ["circuit_id", "proof_type"],
    )

    # Per-user pending job count check (rate limiting in proof request)
    op.create_index(
        "ix_proof_jobs_requester_status",
        "proof_jobs",
        ["requester_hotkey", "status"],
    )

    # Add FK constraint on circuits.org_id -> organizations.id
    # Allow NULL (circuits not scoped to an org) but enforce referential
    # integrity when a value is present.
    op.create_foreign_key(
        "fk_circuits_org_id",
        "circuits",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_circuits_org_id", "circuits", type_="foreignkey")
    op.drop_index("ix_proof_jobs_requester_status", table_name="proof_jobs")
    op.drop_index("ix_proofs_circuit_proof_type", table_name="proofs")
    op.drop_index("ix_circuit_partitions_assigned_prover", table_name="circuit_partitions")
