from datetime import datetime, timezone
from uuid import uuid4

from app.domain.models import (
    AuditLogResponse,
    ConfigVersionResponse,
    EvaluationRunResponse,
    HandoffTicketResponse,
    TaskJobResponse,
    UserResponse,
    WorkflowRunResponse,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[str, tuple[UserResponse, str]] = {}

    def create(self, username, password_hash, role, tenant_ids, *, user_id=None):
        timestamp = now()
        item = UserResponse(
            user_id=user_id or str(uuid4()),
            username=username,
            role=role,
            tenant_ids=list(tenant_ids),
            enabled=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.items[item.user_id] = (item, password_hash)
        return item

    def get_by_username(self, username):
        return next((item for item in self.items.values() if item[0].username == username), None)

    def get_by_id(self, user_id):
        stored = self.items.get(user_id)
        return stored[0] if stored else None

    def list(self):
        return sorted((item[0] for item in self.items.values()), key=lambda item: item.username)

    def update(self, user_id, values, tenant_ids=None):
        stored = self.items.get(user_id)
        if stored is None:
            return None
        user, password_hash = stored
        values = dict(values)
        if "password_hash" in values:
            password_hash = values.pop("password_hash")
        update_values = {**values, "updated_at": now()}
        if tenant_ids is not None:
            update_values["tenant_ids"] = tenant_ids
        user = user.model_copy(update=update_values)
        self.items[user_id] = (user, password_hash)
        return user


class MemoryConfigRepository:
    def __init__(self) -> None:
        self.items: dict[str, ConfigVersionResponse] = {}

    def create(self, scope_type, scope_id, values, note, actor_id):
        version = (
            max(
                (
                    item.version
                    for item in self.items.values()
                    if item.scope_type == scope_type and item.scope_id == scope_id
                ),
                default=0,
            )
            + 1
        )
        item = ConfigVersionResponse(
            config_id=str(uuid4()),
            scope_type=scope_type,
            scope_id=scope_id,
            version=version,
            status="draft",
            values=values,
            note=note,
            created_by=actor_id,
            created_at=now(),
        )
        self.items[item.config_id] = item
        return item

    def list(self, scope_type=None, scope_id=None):
        return sorted(
            (
                item
                for item in self.items.values()
                if (scope_type is None or item.scope_type == scope_type)
                and (scope_id is None or item.scope_id == scope_id)
            ),
            key=lambda item: item.created_at,
            reverse=True,
        )

    def publish(self, config_id):
        target = self.items.get(config_id)
        if target is None:
            return None
        for item_id, item in list(self.items.items()):
            if (
                item.scope_type == target.scope_type
                and item.scope_id == target.scope_id
                and item.status == "published"
            ):
                self.items[item_id] = item.model_copy(update={"status": "archived"})
        target = target.model_copy(update={"status": "published", "published_at": now()})
        self.items[config_id] = target
        return target

    def published(self, scope_type="platform", scope_id="global"):
        return next(
            (
                item
                for item in self.items.values()
                if item.scope_type == scope_type
                and item.scope_id == scope_id
                and item.status == "published"
            ),
            None,
        )


class MemoryTaskRepository:
    def __init__(self) -> None:
        self.items: dict[str, TaskJobResponse] = {}

    def create(self, task_id, task_name, payload, max_attempts):
        timestamp = now()
        item = TaskJobResponse(
            task_id=task_id,
            task_name=task_name,
            status="queued",
            payload=payload,
            attempts=0,
            max_attempts=max_attempts,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.items[task_id] = item
        return item

    def update(self, task_id, **values):
        item = self.items.get(task_id)
        if item is None:
            return None
        item = item.model_copy(update={**values, "updated_at": now()})
        self.items[task_id] = item
        return item

    def list(self, limit=100):
        return sorted(self.items.values(), key=lambda item: item.created_at, reverse=True)[:limit]


class MemoryEvaluationRepository:
    def __init__(self) -> None:
        self.items: list[EvaluationRunResponse] = []

    def save(self, report, judge, model_name, plugin_id, workflow_version):
        item = EvaluationRunResponse(
            run_id=str(uuid4()),
            judge=judge,
            model_name=model_name,
            plugin_id=plugin_id,
            workflow_version=workflow_version,
            overall_score=report.overall_score,
            dataset_size=report.dataset_size,
            report=report,
            created_at=now(),
        )
        self.items.append(item)
        return item

    def list(self, limit=50):
        return list(reversed(self.items[-limit:]))


class MemoryWorkflowRepository:
    def __init__(self) -> None:
        self.items: list[WorkflowRunResponse] = []

    def record(self, conversation_id, tenant_id, workflow_version, status, steps):
        item = WorkflowRunResponse(
            run_id=str(uuid4()),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            workflow_version=workflow_version,
            status=status,
            steps=steps,
            created_at=now(),
        )
        self.items.append(item)
        return item

    def list(self, limit=100):
        return list(reversed(self.items[-limit:]))


class MemoryAuditRepository:
    def __init__(self) -> None:
        self.items: list[AuditLogResponse] = []

    def record(
        self, actor_id, action, resource_type, resource_id=None, tenant_id=None, details=None
    ):
        self.items.append(
            AuditLogResponse(
                audit_id=str(uuid4()),
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                tenant_id=tenant_id,
                details=details or {},
                created_at=now(),
            )
        )

    def list(self, tenant_id=None, limit=100):
        items = [item for item in self.items if tenant_id is None or item.tenant_id == tenant_id]
        return list(reversed(items[-limit:]))


class MemoryHandoffRepository:
    def __init__(self) -> None:
        self.items: dict[str, HandoffTicketResponse] = {}

    def create(self, tenant_id, reason, conversation_id=None):
        item = HandoffTicketResponse(
            ticket_id=str(uuid4()),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=reason,
            created_at=now(),
        )
        self.items[item.ticket_id] = item
        return item

    def list(self, tenant_id=None, limit=100):
        items = [
            item for item in self.items.values() if tenant_id is None or item.tenant_id == tenant_id
        ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]

    def update_status(self, ticket_id, status):
        item = self.items.get(ticket_id)
        if item is None:
            return None
        item = item.model_copy(update={"status": status})
        self.items[ticket_id] = item
        return item
