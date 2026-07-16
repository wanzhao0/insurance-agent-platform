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

    def seed_defaults(self) -> None:
        if not self._knowledge_bases:
            self._knowledge_bases.update(
            {
                "insurance-general": KnowledgeBase(
                    knowledge_base_id="insurance-general",
                    tenant_id="demo",
                    name="保险通用知识库",
                    description="用于演示的保险产品、理赔和服务知识。",
                ),
                "motor-service": KnowledgeBase(
                    knowledge_base_id="motor-service",
                    tenant_id="demo",
                    name="车险服务知识库",
                    description="车险报案、事故处理和查勘定损指引。",
                    version=4,
                ),
                "health-products": KnowledgeBase(
                    knowledge_base_id="health-products",
                    tenant_id="demo",
                    name="健康险产品知识库",
                    description="医疗险、重疾险产品说明和服务规则。",
                    version=7,
                ),
                "partner-claims": KnowledgeBase(
                    knowledge_base_id="partner-claims",
                    tenant_id="partner-a",
                    name="合作渠道理赔库",
                    description="合作渠道专属服务和理赔材料。",
                    version=2,
                    enabled=False,
                ),
                }
            )
        if not self._tenants:
            self._tenants.update(
            {
                "demo": TenantConfig(
                    tenant_id="demo",
                    name="启明保险集团",
                    plan="企业版",
                    default_knowledge_base_id="insurance-general",
                    settings={"display_name": "演示租户", "locale": "zh-CN"},
                ),
                "partner-a": TenantConfig(
                    tenant_id="partner-a",
                    name="安顺渠道合作方",
                    plan="合作版",
                    default_knowledge_base_id="partner-claims",
                ),
                "sandbox": TenantConfig(
                    tenant_id="sandbox",
                    name="产品测试租户",
                    plan="沙箱",
                    default_knowledge_base_id="health-products",
                    enabled=False,
                ),
                }
            )
        self._persist_configuration()
        self.add_document(
            "insurance-general",
            DocumentCreate(
                document_id="demo-claim",
                title="理赔材料提交",
                content="申请理赔通常需要提供保单信息、被保险人身份证明、事故证明和与损失相关的材料。不同产品和事故类型的要求可能不同，请以保单约定和客服审核结果为准。",
                metadata={"category": "claims", "source": "demo"},
            ),
        )
        self.add_document(
            "motor-service",
            DocumentCreate(
                document_id="motor-claim",
                title="车险事故处理指引",
                content="发生交通事故后，请先确保人员安全并按照当地要求报警。报案和材料提交时效以产品条款与服务指引为准。",
                metadata={"category": "claims", "source": "demo"},
            ),
        )
        self.add_document(
            "health-products",
            DocumentCreate(
                document_id="health-reimburse",
                title="医疗费用报销范围",
                content="医疗费用报销范围需要结合产品责任、医院等级、免赔额以及条款约定综合判断。",
                metadata={"category": "policy", "source": "demo"},
            ),
        )
        self.add_document(
            "insurance-general",
            DocumentCreate(
                document_id="demo-cooling-off",
                title="犹豫期说明",
                content="长期人身保险产品可能设置犹豫期。犹豫期的具体天数、退保规则和费用处理以产品条款及投保单约定为准。",
                metadata={"category": "policy", "source": "demo"},
            ),
        )

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
                knowledge_base_count=sum(item.tenant_id == tenant.tenant_id for item in self._knowledge_bases.values()),
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
        return next(item for item in self.list_all() if item.knowledge_base_id == payload.knowledge_base_id)

    def update_knowledge_base(self, knowledge_base_id: str, payload: KnowledgeBaseUpdate) -> KnowledgeBaseResponse:
        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("knowledge base not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(knowledge_base, field, value)
        knowledge_base.version += 1
        self._persist_knowledge_base(knowledge_base)
        return next(item for item in self.list_all() if item.knowledge_base_id == knowledge_base_id)

    def resolve_knowledge_base(self, tenant_id: str, knowledge_base_id: str | None) -> str:
        if knowledge_base_id:
            knowledge_base = self.get(knowledge_base_id)
            if knowledge_base is None or knowledge_base.tenant_id != tenant_id or not knowledge_base.enabled:
                raise ValueError("knowledge base is not available for this tenant")
            return knowledge_base_id
        tenant = self._tenants.get(tenant_id)
        if tenant is None or not tenant.enabled:
            raise ValueError("tenant is not configured")
        available = self.list_for_tenant(tenant_id)
        if not available:
            raise ValueError("tenant has no enabled knowledge base")
        configured_default = next(
            (item for item in available if item.knowledge_base_id == tenant.default_knowledge_base_id), None
        )
        return configured_default.knowledge_base_id if configured_default else available[0].knowledge_base_id

    def add_document(self, knowledge_base_id: str, payload: DocumentCreate) -> DocumentResponse:
        return self.document_repository.add(knowledge_base_id, payload)

    def list_all_documents(self) -> list[DocumentResponse]:
        documents: list[DocumentResponse] = []
        for knowledge_base_id in self._knowledge_bases:
            documents.extend(self.document_repository.list(knowledge_base_id))
        return documents

    def delete_document(self, knowledge_base_id: str, document_id: str) -> bool:
        return self.document_repository.delete(knowledge_base_id, document_id)

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
