"""把插件声明的工作流步骤组装为可执行的多 Agent 流程。"""

from collections.abc import Callable

from app.application.agent.agents import KnowledgeRetrievalAgent, SafetyReviewAgent
from app.application.agent.registry import ToolRegistry
from app.application.workflow.engine import Workflow, WorkflowState
from app.domain.ports import ModelClient
from app.plugins.base import WorkflowStepSpec


class AgentOrchestrator:
    """按行业插件的步骤定义执行一次客服多 Agent 工作流。"""

    def __init__(
        self,
        model_client_provider: Callable[[], ModelClient],
        tool_registry: ToolRegistry,
        definition: tuple[WorkflowStepSpec, ...],
    ) -> None:
        available = {
            "knowledge_retrieval": KnowledgeRetrievalAgent(model_client_provider, tool_registry),
            "safety_review": SafetyReviewAgent(),
        }
        try:
            steps = [(spec, available[spec.name]) for spec in definition]
        except KeyError as exc:
            raise ValueError(f"unknown workflow step: {exc.args[0]}") from exc
        self.workflow = Workflow(steps=steps)

    async def run(self, context) -> WorkflowState:
        """创建本轮独立状态，避免并发请求之间共享 Agent 中间结果。"""
        return await self.workflow.run(WorkflowState(context=context))
