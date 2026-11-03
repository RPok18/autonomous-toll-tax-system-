"""add transaction balance snapshot

Revision ID: 7f2c1d9a6b10
Revises: 4c1a9f2d7e60
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f2c1d9a6b10"
down_revision: Union[str, Sequence[str], None] = "4c1a9f2d7e60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("balance_after_payment", sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "balance_after_payment")
