import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.asyncio import Redis

from app.core.logging import get_logger


logger = get_logger(__name__)


class NullConfigBus:
    instance_id = "local"

    async def start(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        return None

    async def publish(self, config_id: str, scope_type: str, scope_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


class RedisConfigBus:
    channel = "insurance-agent:config-events"

    def __init__(self, url: str) -> None:
        self.redis = Redis.from_url(url, decode_responses=True)
        self.instance_id = str(uuid4())
        self._task: asyncio.Task | None = None

    async def start(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._listen(callback), name="config-event-listener")

    async def publish(self, config_id: str, scope_type: str, scope_id: str) -> None:
        await self.redis.publish(
            self.channel,
            json.dumps(
                {
                    "source": self.instance_id,
                    "config_id": config_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                }
            ),
        )

    async def _listen(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        async with self.redis.pubsub() as pubsub:
            await pubsub.subscribe(self.channel)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    if event.get("source") != self.instance_id:
                        await callback(event)
                except Exception:
                    logger.exception("config_event_failed")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.redis.aclose()


def build_config_bus(redis_url: str | None):
    return RedisConfigBus(redis_url) if redis_url else NullConfigBus()
