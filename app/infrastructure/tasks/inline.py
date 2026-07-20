"""开发环境的空任务队列实现。"""

from uuid import uuid4


class InlineTaskQueue:
    """只生成任务 ID，不在后台消费；开发环境会在调用方直接完成相应工作。"""

    async def enqueue(self, task_name: str, payload: dict) -> str:
        return f"inline-{task_name}-{uuid4()}"

    async def close(self) -> None:
        return None
