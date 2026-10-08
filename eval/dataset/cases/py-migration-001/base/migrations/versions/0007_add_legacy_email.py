"""Add users.legacy_email."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.add_column("users", sa.Column("legacy_email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "legacy_email")
