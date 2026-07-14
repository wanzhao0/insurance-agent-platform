from uuid import uuid4


class InlineTaskQueue:
    """Development adapter; production can replace this with Redis, Celery, or a broker."""

    async def enqueue(self, task_name: str, payload: dict) -> str:
        return f"inline-{task_name}-{uuid4()}"
