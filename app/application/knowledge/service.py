"""租户、知识库和文档元数据的应用服务。"""

from dataclasses import dataclass
from typing import Any

from app.domain.models import (
    DocumentCreate,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    TenantConfigResponse,
    TenantConfigUpdate,
    TenantSummaryResponse,
)
from app.domain.ports import DocumentRepository, VectorStore
from app.plugins.base import DomainPlugin


@dataclass
class KnowledgeBase:
    knowledge_base_id: str
    tenant_id: str
    name: str
    description: str
    version: int = 1
    enabled: bool = True


@dataclass
class TenantConfig:
    tenant_id: str
    default_knowledge_base_id: str
    name: str
    plan: str
    version: int = 1
    enabled: bool = True
    settings: dict[str, object] | None = None


class KnowledgeBaseService:
    """维护内存中的租户/知识库目录，并委托仓库保存实际数据。

    目录会在进程启动时从数据库恢复，随后再由领域插件补齐默认配置。
    """

    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore,
        persistence: Any | None = None,
    ) -> None:
        self.document_repository = document_repository
        self.vector_store = vector_store
        self.persistence = persistence
        self._knowledge_bases: dict[str, KnowledgeBase] = {}
        self._tenants: dict[str, TenantConfig] = {}
        if persistence is not None:
            self._knowledge_bases = {
                row["knowledge_base_id"]: KnowledgeBase(
                    knowledge_base_id=row["knowledge_base_id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    description=row["description"],
                    version=row["version"],
                    enabled=row["enabled"],
                )
                for row in persistence.load_knowledge_bases()
            }
            self._tenants = {
                row["tenant_id"]: TenantConfig(
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    plan=row["plan"],
                    default_knowledge_base_id=row["default_knowledge_base_id"],
                    version=row["version"],
                    enabled=row["enabled"],
                    settings=row.get("settings") or {},
                )
                for row in persistence.load_tenants()
            }

    def seed_defaults(self, plugin: DomainPlugin) -> None:
        """幂等地补齐插件提供的默认数据。

        `setdefault` 的含义是“已有业务数据优先”，因此重启服务不会反复增加已有文档版本。
        """
        for item in plugin.knowledge_bases:
            self._knowledge_bases.setdefault(
                item.knowledge_base_id,
                KnowledgeBase(
                    knowledge_base_id=item.knowledge_base_id,
                    tenant_id=item.tenant_id,
                    name=item.name,
                    description=item.description,
                    version=item.version,
                    enabled=item.enabled,
                ),
            )

        for item in plugin.tenants:
            self._tenants.setdefault(
                item.tenant_id,
                TenantConfig(
                    tenant_id=item.tenant_id,
                    name=item.name,
                    plan=item.plan,
                    default_knowledge_base_id=item.default_knowledge_base_id,
                    version=item.version,
                    enabled=item.enabled,
                    settings=dict(item.settings),
                ),
            )

        for tenant in self._tenants.values():
            configured_default = self._knowledge_bases.get(tenant.default_knowledge_base_id)
            if configured_default is not None and configured_default.tenant_id == tenant.tenant_id:
                continue
            owned_knowledge_base = next(
                (
                    item
                    for item in self._knowledge_bases.values()
                    if item.tenant_id == tenant.tenant_id
                ),
                None,
            )
            if owned_knowledge_base is not None:
                tenant.default_knowledge_base_id = owned_knowledge_base.knowledge_base_id
                tenant.version += 1
        self._persist_configuration()
        for seed in plugin.documents:
            self._seed_document(seed.knowledge_base_id, seed.document)

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None:
        return self._knowledge_bases.get(knowledge_base_id)

    def tenant_config(self, tenant_id: str) -> TenantConfigResponse | None:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return None
        return TenantConfigResponse(
            tenant_id=tenant.tenant_id,
            default_knowledge_base_id=tenant.default_knowledge_base_id,
            version=tenant.version,
            enabled=tenant.enabled,
            settings=tenant.settings or {},
        )

    def list_tenants(self) -> list[TenantSummaryResponse]:
        return [
            TenantSummaryResponse(
                tenant_id=tenant.tenant_id,
                name=tenant.name,
                plan=tenant.plan,
                default_knowledge_base_id=tenant.default_knowledge_base_id,
                knowledge_base_count=sum(
                    item.tenant_id == tenant.tenant_id for item in self._knowledge_bases.values()
                ),
                version=tenant.version,
                enabled=tenant.enabled,
            )
            for tenant in self._tenants.values()
        ]

    def update_tenant(self, tenant_id: str, payload: TenantConfigUpdate) -> TenantSummaryResponse:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError("tenant not found")
        updates = payload.model_dump(exclude_unset=True)
        default_kb = updates.get("default_knowledge_base_id")
        if default_kb is not None:
            knowledge_base = self._knowledge_bases.get(default_kb)
            if knowledge_base is None or knowledge_base.tenant_id != tenant_id:
                raise ValueError("default knowledge base does not belong to tenant")
            tenant.default_knowledge_base_id = default_kb
        for field in ("name", "plan", "enabled"):
            if field in updates:
                setattr(tenant, field, updates[field])
        if "settings" in updates:
            tenant.settings = updates["settings"]
        tenant.version += 1
        self._persist_tenant(tenant)
        return next(item for item in self.list_tenants() if item.tenant_id == tenant_id)

    def list_for_tenant(self, tenant_id: str) -> list[KnowledgeBaseResponse]:
        return [
            KnowledgeBaseResponse(
                knowledge_base_id=kb.knowledge_base_id,
                tenant_id=kb.tenant_id,
                name=kb.name,
                description=kb.description,
                version=kb.version,
                document_count=len(self.document_repository.list(kb.knowledge_base_id)),
                enabled=kb.enabled,
            )
            for kb in self._knowledge_bases.values()
            if kb.tenant_id == tenant_id and kb.enabled
        ]

    def list_all(self) -> list[KnowledgeBaseResponse]:
        return [
            KnowledgeBaseResponse(
                knowledge_base_id=kb.knowledge_base_id,
                tenant_id=kb.tenant_id,
                name=kb.name,
                description=kb.description,
                version=kb.version,
                document_count=len(self.document_repository.list(kb.knowledge_base_id)),
                enabled=kb.enabled,
            )
            for kb in self._knowledge_bases.values()
        ]

    def create_knowledge_base(self, payload: KnowledgeBaseCreate) -> KnowledgeBaseResponse:
        if payload.knowledge_base_id in self._knowledge_bases:
            raise ValueError("knowledge base already exists")
        if payload.tenant_id not in self._tenants:
            raise ValueError("tenant not found")
        self._knowledge_bases[payload.knowledge_base_id] = KnowledgeBase(**payload.model_dump())
        self._persist_knowledge_base(self._knowledge_bases[payload.knowledge_base_id])
        return next(
            item for item in self.list_all() if item.knowledge_base_id == payload.knowledge_base_id
        )

    def update_knowledge_base(
        self, knowledge_base_id: str, payload: KnowledgeBaseUpdate
    ) -> KnowledgeBaseResponse:
        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("knowledge base not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(knowledge_base, field, value)
        knowledge_base.version += 1
        self._persist_knowledge_base(knowledge_base)
        return next(item for item in self.list_all() if item.knowledge_base_id == knowledge_base_id)

    def resolve_knowledge_base(self, tenant_id: str, knowledge_base_id: str | None) -> str:
        """返回当前租户真正可用的知识库 ID。

        客户端即使传了知识库 ID，也必须属于该租户且处于启用状态。这是租户隔离的核心入口。
        """
        if knowledge_base_id:
            knowledge_base = self.get(knowledge_base_id)
            if (
                knowledge_base is None
                or knowledge_base.tenant_id != tenant_id
                or not knowledge_base.enabled
            ):
                raise ValueError("knowledge base is not available for this tenant")
            return knowledge_base_id
        tenant = self._tenants.get(tenant_id)
        if tenant is None or not tenant.enabled:
            raise ValueError("tenant is not configured")
        available = self.list_for_tenant(tenant_id)
        if not available:
            raise ValueError("tenant has no enabled knowledge base")
        configured_default = next(
            (
                item
                for item in available
                if item.knowledge_base_id == tenant.default_knowledge_base_id
            ),
            None,
        )
        return (
            configured_default.knowledge_base_id
            if configured_default
            else available[0].knowledge_base_id
        )

    def add_document(self, knowledge_base_id: str, payload: DocumentCreate) -> DocumentResponse:
        return self.document_repository.add(knowledge_base_id, payload)

    def list_all_documents(self) -> list[DocumentResponse]:
        documents: list[DocumentResponse] = []
        for knowledge_base_id in self._knowledge_bases:
            documents.extend(self.document_repository.list(knowledge_base_id))
        return documents

    def delete_document(self, knowledge_base_id: str, document_id: str) -> bool:
        return self.document_repository.delete(knowledge_base_id, document_id)

    def _seed_document(self, knowledge_base_id: str, payload: DocumentCreate) -> None:
        if self.document_repository.get(knowledge_base_id, payload.document_id) is None:
            self.add_document(knowledge_base_id, payload)

    def _persist_configuration(self) -> None:
        for tenant in self._tenants.values():
            self._persist_tenant(tenant)
        for knowledge_base in self._knowledge_bases.values():
            self._persist_knowledge_base(knowledge_base)

    def _persist_tenant(self, tenant: TenantConfig) -> None:
        if self.persistence is not None:
            self.persistence.save_tenant(
                {
                    "tenant_id": tenant.tenant_id,
                    "name": tenant.name,
                    "plan": tenant.plan,
                    "default_knowledge_base_id": tenant.default_knowledge_base_id,
                    "version": tenant.version,
                    "enabled": tenant.enabled,
                    "settings": tenant.settings or {},
                }
            )

    def _persist_knowledge_base(self, knowledge_base: KnowledgeBase) -> None:
        if self.persistence is not None:
            self.persistence.save_knowledge_base(
                {
                    "knowledge_base_id": knowledge_base.knowledge_base_id,
                    "tenant_id": knowledge_base.tenant_id,
                    "name": knowledge_base.name,
                    "description": knowledge_base.description,
                    "version": knowledge_base.version,
                    "enabled": knowledge_base.enabled,
                }
            )
