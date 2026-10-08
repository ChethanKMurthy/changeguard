"""Drop users.legacy_email."""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.drop_column("users", "legacy_email")


def downgrade() -> None:
    raise NotImplementedError("legacy_email data cannot be restored")
