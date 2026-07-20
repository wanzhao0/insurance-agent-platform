"""基于 Redis Streams 的可靠异步任务队列。

消费者组会保留已读取但尚未确认的消息。这样 worker 崩溃后，其他 worker 可以认领
超时任务，避免普通 list 队列中“取出即丢失”的风险。
"""

import json
import socket
import time
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError


class RedisTaskQueue:
    """提供入队、确认、重试和死信队列的任务端口实现。"""

    stream_name = "insurance-agent:tasks"
    dead_letter_stream = "insurance-agent:tasks:dead-letter"
    delayed_tasks = "insurance-agent:tasks:delayed"
    group_name = "insurance-agent-workers"

    def __init__(self, url: str) -> None:
        self.redis = Redis.from_url(url, decode_responses=True)
        self.consumer_name = f"{socket.gethostname()}-{uuid4()}"
        self._group_ready = False

    async def _ensure_group(self) -> None:
        """惰性创建消费者组；多个 worker 同时启动时允许其中一个先创建成功。"""
        if self._group_ready:
            return
        try:
            await self.redis.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def enqueue(
        self, task_name: str, payload: dict, *, task_id: str | None = None, attempts: int = 0
    ) -> str:
        task_id = task_id or str(uuid4())
        await self.redis.xadd(
            self.stream_name,
            {
                "task_id": task_id,
                "task_name": task_name,
                "payload": json.dumps(payload, ensure_ascii=False),
                "attempts": str(attempts),
            },
        )
        return task_id

    async def dequeue(self, timeout: int = 5) -> dict | None:
        """优先认领超时的未确认任务，再读取新任务。

        ``XAUTOCLAIM`` 是故障恢复的关键：当某个 worker 在处理过程中退出，消息不会
        永远停留在它的 pending 列表中。
        """
        await self._ensure_group()
        await self._promote_delayed()
        claimed = await self.redis.xautoclaim(
            self.stream_name,
            self.group_name,
            self.consumer_name,
            min_idle_time=60_000,
            start_id="0-0",
            count=1,
        )
        messages = claimed[1] if len(claimed) > 1 else []
        if not messages:
            response = await self.redis.xreadgroup(
                self.group_name,
                self.consumer_name,
                {self.stream_name: ">"},
                count=1,
                block=timeout * 1000,
            )
            messages = response[0][1] if response else []
        if not messages:
            return None
        message_id, fields = messages[0]
        return {
            "message_id": message_id,
            "task_id": fields["task_id"],
            "task_name": fields["task_name"],
            "payload": json.loads(fields["payload"]),
            "attempts": int(fields.get("attempts", 0)),
        }

    async def ack(self, task: dict) -> None:
        """确认任务成功，并删除 Streams 中已不再需要的消息。"""
        await self.redis.xack(self.stream_name, self.group_name, task["message_id"])
        await self.redis.xdel(self.stream_name, task["message_id"])

    async def retry(
        self,
        task: dict,
        error: str,
        max_attempts: int,
        delay_seconds: int = 0,
    ) -> str:
        """根据尝试次数决定立即重试、延迟重试或转入死信队列。"""
        next_attempt = int(task.get("attempts", 0)) + 1
        if next_attempt >= max_attempts:
            await self.redis.xadd(
                self.dead_letter_stream,
                {
                    "task_id": task["task_id"],
                    "task_name": task["task_name"],
                    "payload": json.dumps(task["payload"], ensure_ascii=False),
                    "attempts": str(next_attempt),
                    "error": error[:4000],
                },
            )
            await self.ack(task)
            return "dead_letter"
        if delay_seconds > 0:
            message = json.dumps(
                {
                    "task_id": task["task_id"],
                    "task_name": task["task_name"],
                    "payload": task["payload"],
                    "attempts": next_attempt,
                },
                ensure_ascii=False,
            )
            await self.redis.zadd(self.delayed_tasks, {message: time.time() + delay_seconds})
        else:
            await self.enqueue(
                task["task_name"],
                task["payload"],
                task_id=task["task_id"],
                attempts=next_attempt,
            )
        await self.ack(task)
        return "retrying"

    async def _promote_delayed(self) -> None:
        """把到期的延迟任务从有序集合重新投递到主 Stream。"""
        messages = await self.redis.zrangebyscore(
            self.delayed_tasks, 0, time.time(), start=0, num=100
        )
        for encoded in messages:
            payload = json.loads(encoded)
            await self.enqueue(
                payload["task_name"],
                payload["payload"],
                task_id=payload["task_id"],
                attempts=payload["attempts"],
            )
            await self.redis.zrem(self.delayed_tasks, encoded)

    async def close(self) -> None:
        await self.redis.aclose()
