from dataclasses import dataclass, field
from pathlib import Path

from app.domain.models import DocumentCreate


@dataclass(frozen=True)
class WorkflowStepSpec:
    name: str
    timeout_seconds: float = 45.0
    on_error: str = "stop"


@dataclass(frozen=True)
class PluginKnowledgeBase:
    knowledge_base_id: str
    tenant_id: str
    name: str
    description: str
    version: int = 1
    enabled: bool = True


@dataclass(frozen=True)
class PluginTenant:
    tenant_id: str
    name: str
    plan: str
    default_knowledge_base_id: str
    version: int = 1
    enabled: bool = True
    settings: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginDocument:
    knowledge_base_id: str
    document: DocumentCreate


@dataclass(frozen=True)
class DomainPlugin:
    plugin_id: str
    name: str
    version: str
    workflow_version: str
    system_prompt: str
    workflow: tuple[WorkflowStepSpec, ...]
    tool_names: tuple[str, ...]
    policy_categories: frozenset[str]
    tenants: tuple[PluginTenant, ...]
    knowledge_bases: tuple[PluginKnowledgeBase, ...]
    documents: tuple[PluginDocument, ...]
    evaluation_dataset: Path
