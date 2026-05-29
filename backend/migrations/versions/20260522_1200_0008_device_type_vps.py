"""Add 'vps' to the device_type enum.

Lets vLab register Proxmox VPS (virtual servers) as bookable resources,
alongside the existing FPGA / Jetson / RPi kits. First real VPS pool:
sv21 / sv22 / sv23 on the BCSE i7 Proxmox node (192.168.2.210).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-22 12:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 12+ allows ADD VALUE inside a transaction.
    op.execute("ALTER TYPE device_type ADD VALUE IF NOT EXISTS 'vps'")


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum type — no-op.
    # Reverting would require recreating the type and rewriting the column.
    pass
