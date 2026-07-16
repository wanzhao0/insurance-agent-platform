import json
from uuid import uuid4

from redis.asyncio import Redis


class RedisTaskQueue:
    queue_name = "insurance-agent:tasks"

    def __init__(self, url: str) -> None:
        self.redis = Redis.from_url(url, decode_responses=True)

    async def enqueue(self, task_name: str, payload: dict) -> str:
        task_id = str(uuid4())
        await self.redis.lpush(
            self.queue_name,
            json.dumps({"task_id": task_id, "task_name": task_name, "payload": payload}, ensure_ascii=False),
        )
        return task_id

    async def dequeue(self, timeout: int = 5) -> dict | None:
        item = await self.redis.brpop(self.queue_name, timeout=timeout)
        return json.loads(item[1]) if item else None

    async def close(self) -> None:
        await self.redis.aclose()
