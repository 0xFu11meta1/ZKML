"""add missing constraints and indexes for ZK tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-10

Adds:
- Unique constraint on (job_id, partition_index) in circuit_partitions
- Unique index on (name, version) in circuits
- Index on proof_jobs.created_at for listing queries
- Index on proofs.prover_hotkey for per-prover lookups
- NOT NULL on circuit_partitions.total_partitions
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prevent duplicate partition assignments within the same job
    op.create_unique_constraint(
        "uq_circuit_partitions_job_partition",
        "circuit_partitions",
        ["job_id", "partition_index"],
    )

    # Unique index on circuit name+version for fast duplicate checks
    op.create_unique_constraint(
        "uq_circuits_name_version",
        "circuits",
        ["name", "version"],
    )

    # Faster listing queries ordered by creation time
    op.create_index(
        "ix_proof_jobs_created_at",
        "proof_jobs",
        ["created_at"],
    )

    # Per-prover proof lookups
    op.create_index(
        "ix_proofs_prover_hotkey",
        "proofs",
        ["prover_hotkey"],
    )


def downgrade() -> None:
    op.drop_index("ix_proofs_prover_hotkey", table_name="proofs")
    op.drop_index("ix_proof_jobs_created_at", table_name="proof_jobs")
    op.drop_constraint("uq_circuits_name_version", "circuits", type_="unique")
    op.drop_constraint("uq_circuit_partitions_job_partition", "circuit_partitions", type_="unique")
