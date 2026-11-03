"""add vehicle balance

Revision ID: 4c1a9f2d7e60
Revises: 94170a58f241
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c1a9f2d7e60"
down_revision: Union[str, Sequence[str], None] = "94170a58f241"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("balance", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_vehicles_nonnegative_balance",
        "vehicles",
        "balance >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_vehicles_nonnegative_balance", "vehicles", type_="check")
    op.drop_column("vehicles", "balance")
