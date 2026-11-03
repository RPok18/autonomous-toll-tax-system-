"""add exception resolution note

Revision ID: b7d4e2f1c903
Revises: 9b3f6c1d4a27
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d4e2f1c903"
down_revision: Union[str, Sequence[str], None] = ("9b3f6c1d4a27", "7f2c1d9a6b10")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("exceptions", sa.Column("resolution_note", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("exceptions", "resolution_note")
