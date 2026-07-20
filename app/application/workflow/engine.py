import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.models import ChatMessage, ModelToolCall, SearchResult, WorkflowStepTrace
from app.plugins.base import WorkflowStepSpec
from app.core.metrics import WORKFLOW_STEPS, WORKFLOW_STEP_DURATION


@dataclass
class WorkflowState:
    context: Any
    messages: list[ChatMessage] = field(default_factory=list)
    retrieved: list[SearchResult] = field(default_factory=list)
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    answer: str = ""
    review_reason: str = ""
    traces: list[WorkflowStepTrace] = field(default_factory=list)


class WorkflowStep(Protocol):
    name: str

    async def run(self, state: WorkflowState) -> None: ...


class WorkflowExecutionError(RuntimeError):
    def __init__(self, state: WorkflowState, cause: Exception) -> None:
        self.state = state
        self.cause = cause
        super().__init__(str(cause))


class Workflow:
    def __init__(self, steps: list[tuple[WorkflowStepSpec, WorkflowStep]]) -> None:
        self.steps = steps

    async def run(self, state: WorkflowState) -> WorkflowState:
        for spec, step in self.steps:
            started = time.perf_counter()
            try:
                async with asyncio.timeout(spec.timeout_seconds):
                    await step.run(state)
                state.traces.append(
                    WorkflowStepTrace(
                        step=spec.name,
                        status="succeeded",
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                )
                WORKFLOW_STEPS.labels(spec.name, "succeeded").inc()
                WORKFLOW_STEP_DURATION.labels(spec.name).observe(time.perf_counter() - started)
            except Exception as exc:
                state.traces.append(
                    WorkflowStepTrace(
                        step=spec.name,
                        status="failed",
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        error=str(exc),
                    )
                )
                WORKFLOW_STEPS.labels(spec.name, "failed").inc()
                WORKFLOW_STEP_DURATION.labels(spec.name).observe(time.perf_counter() - started)
                if spec.on_error != "continue":
                    raise WorkflowExecutionError(state, exc) from exc
        return state
