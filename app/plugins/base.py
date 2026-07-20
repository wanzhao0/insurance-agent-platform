"""行业插件的静态配置结构。

插件不是新的 Web 服务，而是一组领域差异：提示词、工作流、允许的工具、默认数据和评测集。
保险只是其中一个实现，核心聊天/检索代码不会写死保险规则。
"""

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
    """一个可替换行业所需的最小配置集合。"""

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
