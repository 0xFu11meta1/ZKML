"""Add soft-delete and proof format version fields.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("circuits", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proofs", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proofs", sa.Column("format_version", sa.Integer(), nullable=True, server_default="1"))

    # Backfill existing rows
    op.execute("UPDATE proofs SET format_version = 1 WHERE format_version IS NULL")

    # Make non-nullable after backfill
    with op.batch_alter_table("proofs") as batch_op:
        batch_op.alter_column("format_version", nullable=False, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("proofs") as batch_op:
        batch_op.drop_column("format_version")
    op.drop_column("proofs", "deleted_at")
    op.drop_column("circuits", "deleted_at")
