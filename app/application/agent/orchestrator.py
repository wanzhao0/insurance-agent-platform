from collections.abc import Callable

from app.application.agent.agents import KnowledgeRetrievalAgent, SafetyReviewAgent
from app.application.agent.registry import ToolRegistry
from app.application.workflow.engine import Workflow, WorkflowState
from app.domain.ports import ModelClient


class AgentOrchestrator:
    """Runs the configured multi-agent workflow for a customer-service turn."""

    def __init__(self, model_client_provider: Callable[[], ModelClient], tool_registry: ToolRegistry) -> None:
        self.workflow = Workflow(
            steps=[
                KnowledgeRetrievalAgent(model_client_provider, tool_registry),
                SafetyReviewAgent(),
            ]
        )

    async def run(self, context) -> WorkflowState:
        return await self.workflow.run(WorkflowState(context=context))
