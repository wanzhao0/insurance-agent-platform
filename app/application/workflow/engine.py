"""声明式工作流执行器。

工作流步骤由领域插件或运行配置给出；执行器只处理顺序、超时、失败策略和运行轨迹，不耦合保险业务。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.models import ChatMessage, ModelToolCall, SearchResult, WorkflowStepTrace
from app.plugins.base import WorkflowStepSpec
from app.core.metrics import WORKFLOW_STEPS, WORKFLOW_STEP_DURATION


@dataclass
class WorkflowState:
    """在一个工作流步骤之间传递的可变状态。"""

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
    """保留失败前轨迹的异常，便于上层把失败运行持久化。"""

    def __init__(self, state: WorkflowState, cause: Exception) -> None:
        self.state = state
        self.cause = cause
        super().__init__(str(cause))


class Workflow:
    """按配置顺序执行 Agent 步骤，并为每一步记录耗时。"""

    def __init__(self, steps: list[tuple[WorkflowStepSpec, WorkflowStep]]) -> None:
        self.steps = steps

    async def run(self, state: WorkflowState) -> WorkflowState:
        for spec, step in self.steps:
            started = time.perf_counter()
            try:
                # 单个步骤超时不应无限占用请求；超时后根据 on_error 决定停止或继续。
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
