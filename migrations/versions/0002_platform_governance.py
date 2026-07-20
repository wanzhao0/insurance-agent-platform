"""add governance records and document lifecycle

Revision ID: 0002_platform_governance
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.infrastructure.persistence.sqlalchemy import metadata


revision = "0002_platform_governance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "users",
    "user_tenants",
    "config_versions",
    "task_jobs",
    "evaluation_runs",
    "workflow_runs",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in NEW_TABLES:
        if table_name not in existing_tables:
            metadata.tables[table_name].create(bind)

    existing_columns = {column["name"] for column in inspect(bind).get_columns("documents")}
    with op.batch_alter_table("documents") as batch:
        if "status" not in existing_columns:
            batch.add_column(
                sa.Column("status", sa.String(length=20), nullable=False, server_default="ready")
            )
        if "source_uri" not in existing_columns:
            batch.add_column(sa.Column("source_uri", sa.Text(), nullable=True))
        if "checksum" not in existing_columns:
            batch.add_column(sa.Column("checksum", sa.String(length=128), nullable=True))
        if "index_version" not in existing_columns:
            batch.add_column(sa.Column("index_version", sa.String(length=200), nullable=True))
        if "updated_at" not in existing_columns:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in inspect(bind).get_columns("documents")}
    with op.batch_alter_table("documents") as batch:
        for column_name in ("updated_at", "index_version", "checksum", "source_uri", "status"):
            if column_name in existing_columns:
                batch.drop_column(column_name)

    existing_tables = set(inspect(bind).get_table_names())
    for table_name in reversed(NEW_TABLES):
        if table_name in existing_tables:
            metadata.tables[table_name].drop(bind)
