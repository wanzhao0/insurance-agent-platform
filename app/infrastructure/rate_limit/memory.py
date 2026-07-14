import asyncio
import time


class InMemoryRateLimiter:
    """Single-process fallback; replace with Redis for multi-instance deployments."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    def reconfigure(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            started, count = self._windows.get(key, (now, 0))
            if now - started >= self.window_seconds:
                started, count = now, 0
            if count >= self.max_requests:
                self._windows[key] = (started, count)
                return False
            self._windows[key] = (started, count + 1)
            return True
