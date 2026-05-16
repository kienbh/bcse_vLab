"""M5.8 follow-up: gateway_sessions.password_ciphertext (AES-GCM).

Thầy's requirement: password is generated ONCE per slot and stays constant
for the whole booking window. POST /access on the same booking returns the
same plaintext until the slot ends. To satisfy that without keeping
plaintext, we store an AES-256-GCM ciphertext alongside the bcrypt hash.

- Hash → still used for PAM verify (defence in depth, never decrypted).
- Ciphertext → only decrypted when the booking owner asks via web UI.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-16 23:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gateway_sessions",
        sa.Column("password_ciphertext", sa.LargeBinary, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_sessions", "password_ciphertext")
