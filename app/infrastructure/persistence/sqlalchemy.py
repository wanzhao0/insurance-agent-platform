"""SQLAlchemy 持久化适配器。

表定义描述数据库结构，仓库类负责把领域模型转换为行记录。应用服务只依赖仓库能力，
因此替换为 PostgreSQL、其他 ORM 或远程存储时，不应改动聊天、RAG 等业务编排代码。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError

from app.domain.models import (
    AuditLogResponse,
    ConfigVersionResponse,
    ConversationMessageResponse,
    ConversationResponse,
    DocumentCreate,
    DocumentResponse,
    EvaluationReport,
    EvaluationRunResponse,
    HandoffTicketResponse,
    TaskJobResponse,
    UserResponse,
    WorkflowRunResponse,
)


metadata = MetaData()

tenants = Table(
    "tenants",
    metadata,
    Column("tenant_id", String(100), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("plan", String(50), nullable=False),
    Column("default_knowledge_base_id", String(100), nullable=False),
    Column("version", Integer, nullable=False, default=1),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("settings", JSON, nullable=False, default=dict),
)

knowledge_bases = Table(
    "knowledge_bases",
    metadata,
    Column("knowledge_base_id", String(100), primary_key=True),
    Column("tenant_id", String(100), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("version", Integer, nullable=False, default=1),
    Column("enabled", Boolean, nullable=False, default=True),
)

documents = Table(
    "documents",
    metadata,
    Column("document_id", String(100), primary_key=True),
    Column("knowledge_base_id", String(100), primary_key=True),
    Column("title", String(300), nullable=False),
    Column("content", Text, nullable=False),
    Column("document_metadata", JSON, nullable=False, default=dict),
    Column("version", Integer, nullable=False, default=1),
    Column("status", String(20), nullable=False, default="ready"),
    Column("source_uri", Text),
    Column("checksum", String(128)),
    Column("index_version", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

conversation_messages = Table(
    "conversation_messages",
    metadata,
    Column("message_id", String(100), primary_key=True),
    Column("conversation_id", String(100), index=True, nullable=False),
    Column("tenant_id", String(100), index=True, nullable=False),
    Column("knowledge_base_id", String(100), nullable=False),
    Column("role", String(20), nullable=False),
    Column("content", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("audit_id", String(100), primary_key=True),
    Column("actor_id", String(100), nullable=False),
    Column("action", String(100), nullable=False),
    Column("resource_type", String(100), nullable=False),
    Column("resource_id", String(100)),
    Column("tenant_id", String(100), index=True),
    Column("details", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

handoff_tickets = Table(
    "handoff_tickets",
    metadata,
    Column("ticket_id", String(100), primary_key=True),
    Column("tenant_id", String(100), index=True, nullable=False),
    Column("conversation_id", String(100)),
    Column("reason", Text, nullable=False),
    Column("status", String(30), nullable=False, default="open"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("user_id", String(100), primary_key=True),
    Column("username", String(100), nullable=False, unique=True, index=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(20), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

user_tenants = Table(
    "user_tenants",
    metadata,
    Column("user_id", String(100), primary_key=True),
    Column("tenant_id", String(100), primary_key=True),
)

config_versions = Table(
    "config_versions",
    metadata,
    Column("config_id", String(100), primary_key=True),
    Column("scope_type", String(20), nullable=False, index=True),
    Column("scope_id", String(100), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("config_values", JSON, nullable=False, default=dict),
    Column("note", String(500), nullable=False, default=""),
    Column("created_by", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    UniqueConstraint("scope_type", "scope_id", "version", name="uq_config_scope_version"),
)

task_jobs = Table(
    "task_jobs",
    metadata,
    Column("task_id", String(100), primary_key=True),
    Column("task_name", String(100), nullable=False, index=True),
    Column("status", String(30), nullable=False, index=True),
    Column("payload", JSON, nullable=False, default=dict),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

evaluation_runs = Table(
    "evaluation_runs",
    metadata,
    Column("run_id", String(100), primary_key=True),
    Column("judge", String(20), nullable=False),
    Column("model_name", String(200), nullable=False),
    Column("plugin_id", String(100), nullable=False),
    Column("workflow_version", String(100), nullable=False),
    Column("overall_score", Float, nullable=False),
    Column("dataset_size", Integer, nullable=False),
    Column("report", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

workflow_runs = Table(
    "workflow_runs",
    metadata,
    Column("run_id", String(100), primary_key=True),
    Column("conversation_id", String(100), nullable=False, index=True),
    Column("tenant_id", String(100), nullable=False, index=True),
    Column("workflow_version", String(100), nullable=False),
    Column("status", String(20), nullable=False),
    Column("steps", JSON, nullable=False, default=list),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SqlAlchemyDatabase:
    """管理 SQLAlchemy engine 和表初始化，不承载具体业务查询。"""

    def __init__(
        self,
        url: str,
        echo: bool = False,
        auto_create: bool = True,
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> None:
        if url.startswith("sqlite:///"):
            # SQLite 是本地文件，首次启动前需创建目录；网络数据库由服务端负责存储空间。
            database_path = Path(url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        pool_options = {}
        if not url.startswith("sqlite"):
            # SQLite 的连接模型与服务型数据库不同，连接池参数只对后者生效。
            pool_options = {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_pre_ping": True,
            }
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            connect_args=connect_args,
            **pool_options,
        )
        if auto_create:
            metadata.create_all(self.engine)

    def healthcheck(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def close(self) -> None:
        self.engine.dispose()


class SqlAlchemyDocumentRepository:
    """知识文档仓库，负责文档内容与索引生命周期元数据的持久化。"""

    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def list(self, knowledge_base_id: str) -> list[DocumentResponse]:
        statement = (
            select(documents)
            .where(documents.c.knowledge_base_id == knowledge_base_id)
            .order_by(documents.c.created_at)
        )
        with self.database.engine.connect() as connection:
            return [self._to_document(row) for row in connection.execute(statement).mappings()]

    def get(self, knowledge_base_id: str, document_id: str) -> DocumentResponse | None:
        statement = select(documents).where(
            documents.c.knowledge_base_id == knowledge_base_id,
            documents.c.document_id == document_id,
        )
        with self.database.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return self._to_document(row) if row else None

    def add(self, knowledge_base_id: str, document: DocumentCreate) -> DocumentResponse:
        existing = self.get(knowledge_base_id, document.document_id)
        created_at = existing.created_at if existing else utcnow()
        updated_at = utcnow()
        stored = DocumentResponse(
            **document.model_dump(),
            knowledge_base_id=knowledge_base_id,
            version=existing.version + 1 if existing else 1,
            created_at=created_at,
            status=existing.status if existing else "ready",
            source_uri=existing.source_uri if existing else None,
            checksum=existing.checksum if existing else None,
            index_version=existing.index_version if existing else None,
            updated_at=updated_at,
        )
        values = {
            "document_id": stored.document_id,
            "knowledge_base_id": stored.knowledge_base_id,
            "title": stored.title,
            "content": stored.content,
            "document_metadata": stored.metadata,
            "version": stored.version,
            "status": stored.status,
            "source_uri": stored.source_uri,
            "checksum": stored.checksum,
            "index_version": stored.index_version,
            "created_at": stored.created_at,
            "updated_at": updated_at,
        }
        with self.database.engine.begin() as connection:
            if existing:
                connection.execute(
                    update(documents)
                    .where(
                        documents.c.knowledge_base_id == knowledge_base_id,
                        documents.c.document_id == document.document_id,
                    )
                    .values(**values)
                )
            else:
                connection.execute(insert(documents).values(**values))
        return stored

    def delete(self, knowledge_base_id: str, document_id: str) -> bool:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                delete(documents).where(
                    documents.c.knowledge_base_id == knowledge_base_id,
                    documents.c.document_id == document_id,
                )
            )
        return result.rowcount > 0

    def update_lifecycle(
        self,
        knowledge_base_id: str,
        document_id: str,
        values: dict,
    ) -> DocumentResponse | None:
        """只更新索引流程允许修改的字段，避免后台任务意外覆盖文档正文。"""
        allowed = {"status", "source_uri", "checksum", "index_version"}
        updates = {key: value for key, value in values.items() if key in allowed}
        updates["updated_at"] = utcnow()
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(documents)
                .where(
                    documents.c.knowledge_base_id == knowledge_base_id,
                    documents.c.document_id == document_id,
                )
                .values(**updates)
            )
        return self.get(knowledge_base_id, document_id) if result.rowcount else None

    @staticmethod
    def _to_document(row) -> DocumentResponse:
        return DocumentResponse(
            document_id=row.document_id,
            title=row.title,
            content=row.content,
            metadata=row.document_metadata or {},
            knowledge_base_id=row.knowledge_base_id,
            version=row.version,
            created_at=aware(row.created_at),
            status=row.status,
            source_uri=row.source_uri,
            checksum=row.checksum,
            index_version=row.index_version,
            updated_at=aware(row.updated_at),
        )


class SqlAlchemyKnowledgeStore:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def load_tenants(self) -> list[dict]:
        with self.database.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(tenants).order_by(tenants.c.tenant_id)
                ).mappings()
            ]

    def load_knowledge_bases(self) -> list[dict]:
        with self.database.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(knowledge_bases).order_by(knowledge_bases.c.knowledge_base_id)
                ).mappings()
            ]

    def save_tenant(self, values: dict) -> None:
        self._upsert(tenants, values, tenants.c.tenant_id, values["tenant_id"])

    def save_knowledge_base(self, values: dict) -> None:
        self._upsert(
            knowledge_bases,
            values,
            knowledge_bases.c.knowledge_base_id,
            values["knowledge_base_id"],
        )

    def _upsert(self, table: Table, values: dict, key_column, key_value) -> None:
        with self.database.engine.begin() as connection:
            exists = connection.execute(select(key_column).where(key_column == key_value)).first()
            if exists:
                connection.execute(update(table).where(key_column == key_value).values(**values))
            else:
                connection.execute(insert(table).values(**values))


class SqlAlchemyConversationRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def save_turn(
        self,
        conversation_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        role: str,
        content: str | None,
    ) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(conversation_messages).values(
                    message_id=str(uuid4()),
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    knowledge_base_id=knowledge_base_id,
                    role=role,
                    content=content,
                    created_at=utcnow(),
                )
            )

    def get(self, conversation_id: str) -> ConversationResponse | None:
        statement = (
            select(conversation_messages)
            .where(conversation_messages.c.conversation_id == conversation_id)
            .order_by(conversation_messages.c.created_at)
        )
        with self.database.engine.connect() as connection:
            rows = list(connection.execute(statement).mappings())
        if not rows:
            return None
        messages = [
            ConversationMessageResponse(
                message_id=row.message_id,
                conversation_id=row.conversation_id,
                role=row.role,
                content=row.content,
                created_at=aware(row.created_at),
            )
            for row in rows
        ]
        return ConversationResponse(
            conversation_id=conversation_id,
            tenant_id=rows[0].tenant_id,
            knowledge_base_id=rows[0].knowledge_base_id,
            created_at=aware(rows[0].created_at),
            updated_at=aware(rows[-1].created_at),
            messages=messages,
        )


class SqlAlchemyAuditRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def record(
        self,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        tenant_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(audit_logs).values(
                    audit_id=str(uuid4()),
                    actor_id=actor_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    tenant_id=tenant_id,
                    details=details or {},
                    created_at=utcnow(),
                )
            )

    def list(self, tenant_id: str | None = None, limit: int = 100) -> list[AuditLogResponse]:
        statement = select(audit_logs).order_by(audit_logs.c.created_at.desc()).limit(limit)
        if tenant_id:
            statement = statement.where(audit_logs.c.tenant_id == tenant_id)
        with self.database.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [
                AuditLogResponse(
                    audit_id=row.audit_id,
                    actor_id=row.actor_id,
                    action=row.action,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    tenant_id=row.tenant_id,
                    details=row.details or {},
                    created_at=aware(row.created_at),
                )
                for row in rows
            ]


class SqlAlchemyHandoffRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def create(
        self,
        tenant_id: str,
        reason: str,
        conversation_id: str | None = None,
    ) -> HandoffTicketResponse:
        ticket = HandoffTicketResponse(
            ticket_id=str(uuid4()),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=reason,
            created_at=utcnow(),
        )
        with self.database.engine.begin() as connection:
            connection.execute(insert(handoff_tickets).values(**ticket.model_dump()))
        return ticket

    def list(self, tenant_id: str | None = None, limit: int = 100) -> list[HandoffTicketResponse]:
        statement = (
            select(handoff_tickets).order_by(handoff_tickets.c.created_at.desc()).limit(limit)
        )
        if tenant_id:
            statement = statement.where(handoff_tickets.c.tenant_id == tenant_id)
        with self.database.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [self._to_ticket(row) for row in rows]

    def update_status(self, ticket_id: str, status: str) -> HandoffTicketResponse | None:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(handoff_tickets)
                .where(handoff_tickets.c.ticket_id == ticket_id)
                .values(status=status)
            )
            if result.rowcount == 0:
                return None
            row = (
                connection.execute(
                    select(handoff_tickets).where(handoff_tickets.c.ticket_id == ticket_id)
                )
                .mappings()
                .first()
            )
        return self._to_ticket(row) if row else None

    @staticmethod
    def _to_ticket(row) -> HandoffTicketResponse:
        return HandoffTicketResponse(
            ticket_id=row.ticket_id,
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            reason=row.reason,
            status=row.status,
            created_at=aware(row.created_at),
        )


class SqlAlchemyUserRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def create(
        self,
        username: str,
        password_hash: str,
        role: str,
        tenant_ids: list[str],
        *,
        user_id: str | None = None,
    ) -> UserResponse:
        now = utcnow()
        user_id = user_id or str(uuid4())
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(users).values(
                    user_id=user_id,
                    username=username,
                    password_hash=password_hash,
                    role=role,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            if tenant_ids:
                connection.execute(
                    insert(user_tenants),
                    [{"user_id": user_id, "tenant_id": tenant_id} for tenant_id in tenant_ids],
                )
        return UserResponse(
            user_id=user_id,
            username=username,
            role=role,
            tenant_ids=tenant_ids,
            enabled=True,
            created_at=now,
            updated_at=now,
        )

    def get_by_username(self, username: str) -> tuple[UserResponse, str] | None:
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(select(users).where(users.c.username == username))
                .mappings()
                .first()
            )
            if row is None:
                return None
            tenant_ids = [
                item.tenant_id
                for item in connection.execute(
                    select(user_tenants.c.tenant_id).where(user_tenants.c.user_id == row.user_id)
                )
            ]
        return self._to_user(row, tenant_ids), row.password_hash

    def get_by_id(self, user_id: str) -> UserResponse | None:
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(select(users).where(users.c.user_id == user_id))
                .mappings()
                .first()
            )
            if row is None:
                return None
            tenant_ids = [
                item.tenant_id
                for item in connection.execute(
                    select(user_tenants.c.tenant_id).where(user_tenants.c.user_id == user_id)
                )
            ]
        return self._to_user(row, tenant_ids)

    def list(self) -> list[UserResponse]:
        with self.database.engine.connect() as connection:
            rows = list(connection.execute(select(users).order_by(users.c.username)).mappings())
            memberships = list(connection.execute(select(user_tenants)).mappings())
        by_user: dict[str, list[str]] = {}
        for membership in memberships:
            by_user.setdefault(membership.user_id, []).append(membership.tenant_id)
        return [self._to_user(row, by_user.get(row.user_id, [])) for row in rows]

    def update(
        self, user_id: str, values: dict, tenant_ids: list[str] | None = None
    ) -> UserResponse | None:
        updates = {**values, "updated_at": utcnow()}
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(users).where(users.c.user_id == user_id).values(**updates)
            )
            if result.rowcount == 0:
                return None
            if tenant_ids is not None:
                connection.execute(delete(user_tenants).where(user_tenants.c.user_id == user_id))
                if tenant_ids:
                    connection.execute(
                        insert(user_tenants),
                        [{"user_id": user_id, "tenant_id": tenant_id} for tenant_id in tenant_ids],
                    )
            row = (
                connection.execute(select(users).where(users.c.user_id == user_id))
                .mappings()
                .first()
            )
            memberships = [
                item.tenant_id
                for item in connection.execute(
                    select(user_tenants.c.tenant_id).where(user_tenants.c.user_id == user_id)
                )
            ]
        return self._to_user(row, memberships) if row else None

    @staticmethod
    def _to_user(row, tenant_ids: list[str]) -> UserResponse:
        return UserResponse(
            user_id=row.user_id,
            username=row.username,
            role=row.role,
            tenant_ids=tenant_ids,
            enabled=row.enabled,
            created_at=aware(row.created_at),
            updated_at=aware(row.updated_at),
        )


class SqlAlchemyConfigRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def create(
        self, scope_type: str, scope_id: str, values: dict, note: str, actor_id: str
    ) -> ConfigVersionResponse:
        for attempt in range(5):
            now = utcnow()
            try:
                with self.database.engine.begin() as connection:
                    latest = connection.execute(
                        select(func.max(config_versions.c.version)).where(
                            config_versions.c.scope_type == scope_type,
                            config_versions.c.scope_id == scope_id,
                        )
                    ).scalar_one_or_none()
                    row = {
                        "config_id": str(uuid4()),
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "version": int(latest or 0) + 1,
                        "status": "draft",
                        "config_values": values,
                        "note": note,
                        "created_by": actor_id,
                        "created_at": now,
                        "published_at": None,
                    }
                    connection.execute(insert(config_versions).values(**row))
                return self._to_config(row)
            except IntegrityError:
                if attempt == 4:
                    raise
                time.sleep(0.01 * (attempt + 1))
        raise RuntimeError("could not allocate config version")

    def list(
        self, scope_type: str | None = None, scope_id: str | None = None
    ) -> list[ConfigVersionResponse]:
        statement = select(config_versions).order_by(config_versions.c.created_at.desc())
        if scope_type:
            statement = statement.where(config_versions.c.scope_type == scope_type)
        if scope_id:
            statement = statement.where(config_versions.c.scope_id == scope_id)
        with self.database.engine.connect() as connection:
            return [self._to_config(row) for row in connection.execute(statement).mappings()]

    def publish(self, config_id: str) -> ConfigVersionResponse | None:
        now = utcnow()
        with self.database.engine.begin() as connection:
            target = (
                connection.execute(
                    select(config_versions)
                    .where(config_versions.c.config_id == config_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if target is None:
                return None
            connection.execute(
                select(config_versions.c.config_id)
                .where(
                    config_versions.c.scope_type == target.scope_type,
                    config_versions.c.scope_id == target.scope_id,
                )
                .with_for_update()
            ).all()
            connection.execute(
                update(config_versions)
                .where(
                    config_versions.c.scope_type == target.scope_type,
                    config_versions.c.scope_id == target.scope_id,
                    config_versions.c.status == "published",
                )
                .values(status="archived")
            )
            connection.execute(
                update(config_versions)
                .where(config_versions.c.config_id == config_id)
                .values(status="published", published_at=now)
            )
            row = dict(target)
            row.update(status="published", published_at=now)
        return self._to_config(row)

    def published(
        self, scope_type: str = "platform", scope_id: str = "global"
    ) -> ConfigVersionResponse | None:
        statement = select(config_versions).where(
            config_versions.c.scope_type == scope_type,
            config_versions.c.scope_id == scope_id,
            config_versions.c.status == "published",
        )
        with self.database.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return self._to_config(row) if row else None

    @staticmethod
    def _to_config(row) -> ConfigVersionResponse:
        return ConfigVersionResponse(
            config_id=row["config_id"],
            scope_type=row["scope_type"],
            scope_id=row["scope_id"],
            version=row["version"],
            status=row["status"],
            values=row["config_values"] or {},
            note=row["note"] or "",
            created_by=row["created_by"],
            created_at=aware(row["created_at"]),
            published_at=aware(row["published_at"]) if row["published_at"] else None,
        )


class SqlAlchemyTaskRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def create(
        self, task_id: str, task_name: str, payload: dict, max_attempts: int
    ) -> TaskJobResponse:
        now = utcnow()
        values = {
            "task_id": task_id,
            "task_name": task_name,
            "status": "queued",
            "payload": payload,
            "attempts": 0,
            "max_attempts": max_attempts,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.database.engine.begin() as connection:
            connection.execute(insert(task_jobs).values(**values))
        return TaskJobResponse(**values)

    def update(self, task_id: str, **values) -> TaskJobResponse | None:
        values["updated_at"] = utcnow()
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(task_jobs).where(task_jobs.c.task_id == task_id).values(**values)
            )
            if result.rowcount == 0:
                return None
            row = (
                connection.execute(select(task_jobs).where(task_jobs.c.task_id == task_id))
                .mappings()
                .first()
            )
        return self._to_task(row) if row else None

    def list(self, limit: int = 100) -> list[TaskJobResponse]:
        statement = select(task_jobs).order_by(task_jobs.c.created_at.desc()).limit(limit)
        with self.database.engine.connect() as connection:
            return [self._to_task(row) for row in connection.execute(statement).mappings()]

    @staticmethod
    def _to_task(row) -> TaskJobResponse:
        return TaskJobResponse(
            task_id=row.task_id,
            task_name=row.task_name,
            status=row.status,
            payload=row.payload or {},
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            error=row.error,
            created_at=aware(row.created_at),
            updated_at=aware(row.updated_at),
        )


class SqlAlchemyEvaluationRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def save(
        self,
        report: EvaluationReport,
        judge: str,
        model_name: str,
        plugin_id: str,
        workflow_version: str,
    ) -> EvaluationRunResponse:
        run = EvaluationRunResponse(
            run_id=str(uuid4()),
            judge=judge,
            model_name=model_name,
            plugin_id=plugin_id,
            workflow_version=workflow_version,
            overall_score=report.overall_score,
            dataset_size=report.dataset_size,
            report=report,
            created_at=utcnow(),
        )
        values = {
            "run_id": run.run_id,
            "judge": run.judge,
            "model_name": run.model_name,
            "plugin_id": run.plugin_id,
            "workflow_version": run.workflow_version,
            "overall_score": run.overall_score,
            "dataset_size": run.dataset_size,
            "report": report.model_dump(mode="json"),
            "created_at": run.created_at,
        }
        with self.database.engine.begin() as connection:
            connection.execute(insert(evaluation_runs).values(**values))
        return run

    def list(self, limit: int = 50) -> list[EvaluationRunResponse]:
        statement = (
            select(evaluation_runs).order_by(evaluation_runs.c.created_at.desc()).limit(limit)
        )
        with self.database.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [
                EvaluationRunResponse(
                    run_id=row.run_id,
                    judge=row.judge,
                    model_name=row.model_name,
                    plugin_id=row.plugin_id,
                    workflow_version=row.workflow_version,
                    overall_score=row.overall_score,
                    dataset_size=row.dataset_size,
                    report=EvaluationReport.model_validate(row.report),
                    created_at=aware(row.created_at),
                )
                for row in rows
            ]


class SqlAlchemyWorkflowRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def record(
        self,
        conversation_id: str,
        tenant_id: str,
        workflow_version: str,
        status: str,
        steps: list[dict],
    ) -> WorkflowRunResponse:
        run = WorkflowRunResponse(
            run_id=str(uuid4()),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            workflow_version=workflow_version,
            status=status,
            steps=steps,
            created_at=utcnow(),
        )
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(workflow_runs).values(
                    run_id=run.run_id,
                    conversation_id=run.conversation_id,
                    tenant_id=run.tenant_id,
                    workflow_version=run.workflow_version,
                    status=run.status,
                    steps=[step.model_dump(mode="json") for step in run.steps],
                    created_at=run.created_at,
                )
            )
        return run

    def list(self, limit: int = 100) -> list[WorkflowRunResponse]:
        statement = select(workflow_runs).order_by(workflow_runs.c.created_at.desc()).limit(limit)
        with self.database.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [
                WorkflowRunResponse(
                    run_id=row.run_id,
                    conversation_id=row.conversation_id,
                    tenant_id=row.tenant_id,
                    workflow_version=row.workflow_version,
                    status=row.status,
                    steps=row.steps or [],
                    created_at=aware(row.created_at),
                )
                for row in rows
            ]
