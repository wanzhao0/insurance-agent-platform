from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.models import ChatMessage, ModelToolCall, SearchResult


@dataclass
class WorkflowState:
    context: Any
    messages: list[ChatMessage] = field(default_factory=list)
    retrieved: list[SearchResult] = field(default_factory=list)
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    answer: str = ""
    review_reason: str = ""


class WorkflowStep(Protocol):
    name: str

    async def run(self, state: WorkflowState) -> None: ...


class Workflow:
    def __init__(self, steps: list[WorkflowStep]) -> None:
        self.steps = steps

    async def run(self, state: WorkflowState) -> WorkflowState:
        for step in self.steps:
            await step.run(state)
        return state
