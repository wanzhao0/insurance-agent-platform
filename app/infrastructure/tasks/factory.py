from app.core.config import Settings
from app.infrastructure.tasks.inline import InlineTaskQueue
from app.infrastructure.tasks.redis import RedisTaskQueue


def build_task_queue(settings: Settings):
    if settings.task_queue.lower() == "redis":
        if not settings.redis_url:
            raise ValueError("AGENT_REDIS_URL is required when AGENT_TASK_QUEUE=redis")
        return RedisTaskQueue(settings.redis_url)
    return InlineTaskQueue()
