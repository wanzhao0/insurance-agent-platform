"""create initial agent platform schema"""

from alembic import op

from app.infrastructure.persistence.sqlalchemy import metadata


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
