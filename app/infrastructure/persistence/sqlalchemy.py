from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    text,
    update,
)

from app.domain.models import (
    ConversationMessageResponse,
    ConversationResponse,
    DocumentCreate,
    DocumentResponse,
    HandoffTicketResponse,
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
    Column("created_at", DateTime(timezone=True), nullable=False),
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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SqlAlchemyDatabase:
    def __init__(self, url: str, echo: bool = False, auto_create: bool = True) -> None:
        if url.startswith("sqlite:///"):
            database_path = Path(url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)
        if auto_create:
            metadata.create_all(self.engine)

    def healthcheck(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def close(self) -> None:
        self.engine.dispose()


class SqlAlchemyDocumentRepository:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def list(self, knowledge_base_id: str) -> list[DocumentResponse]:
        statement = select(documents).where(
            documents.c.knowledge_base_id == knowledge_base_id
        ).order_by(documents.c.created_at)
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
        stored = DocumentResponse(
            **document.model_dump(),
            knowledge_base_id=knowledge_base_id,
            version=existing.version + 1 if existing else 1,
            created_at=created_at,
        )
        values = {
            "document_id": stored.document_id,
            "knowledge_base_id": stored.knowledge_base_id,
            "title": stored.title,
            "content": stored.content,
            "document_metadata": stored.metadata,
            "version": stored.version,
            "created_at": stored.created_at,
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
        )


class SqlAlchemyKnowledgeStore:
    def __init__(self, database: SqlAlchemyDatabase) -> None:
        self.database = database

    def load_tenants(self) -> list[dict]:
        with self.database.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(select(tenants).order_by(tenants.c.tenant_id)).mappings()
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
        statement = select(conversation_messages).where(
            conversation_messages.c.conversation_id == conversation_id
        ).order_by(conversation_messages.c.created_at)
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
