"""add exception image and resolved_at

Revision ID: 9b3f6c1d4a27
Revises: 4c1a9f2d7e60
Create Date: 2026-10-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b3f6c1d4a27"
down_revision: Union[str, Sequence[str], None] = "4c1a9f2d7e60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exceptions", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("exceptions", sa.Column("image_path", sa.String(length=255), nullable=True))
    # Exceptions resolved before this column existed: use their creation time as the best estimate.
    op.execute("UPDATE exceptions SET resolved_at = created_at WHERE resolved IS TRUE AND resolved_at IS NULL")


def downgrade() -> None:
    op.drop_column("exceptions", "image_path")
    op.drop_column("exceptions", "resolved_at")
