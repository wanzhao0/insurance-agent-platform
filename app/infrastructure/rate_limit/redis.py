from redis.asyncio import Redis


class RedisRateLimiter:
    def __init__(self, url: str, max_requests: int, window_seconds: int) -> None:
        self.redis = Redis.from_url(url, decode_responses=True)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def reconfigure(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def allow(self, key: str) -> bool:
        redis_key = f"insurance-agent:rate:{key}"
        count = await self.redis.incr(redis_key)
        if count == 1:
            await self.redis.expire(redis_key, self.window_seconds)
        return count <= self.max_requests

    async def close(self) -> None:
        await self.redis.aclose()
