"""跨 API 实例传播已发布配置的通知总线。"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.asyncio import Redis

from app.core.logging import get_logger


logger = get_logger(__name__)


class NullConfigBus:
    """未配置 Redis 时的单机实现；调用方无需为本地开发写分支。"""

    instance_id = "local"

    async def start(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        return None

    async def publish(self, config_id: str, scope_type: str, scope_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


class RedisConfigBus:
    """通过 Redis Pub/Sub 通知其他实例刷新运行时配置。

    数据库中的配置版本才是事实来源；消息只负责提醒各实例重新加载，丢失单条通知也
    不会改变已发布配置本身。
    """

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
        """忽略自己发布的消息，并把其他实例的配置变更交给容器处理。"""
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
    """根据部署配置选择跨实例 Redis 总线或本地空实现。"""
    return RedisConfigBus(redis_url) if redis_url else NullConfigBus()
