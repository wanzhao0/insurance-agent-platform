"""异步任务消费者入口。

Web API 只负责提交耗时任务；本模块在独立进程中消费队列，避免文档解析和建索引
占用用户请求的连接与超时预算。
"""

import asyncio

from prometheus_client import start_http_server

from app.bootstrap.container import build_container
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.tasks.factory import build_task_queue
from app.core.metrics import TASKS


logger = get_logger(__name__)


async def run() -> None:
    """持续消费任务，并把执行状态写回任务仓库供后台查询。"""
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.metrics_enabled:
        start_http_server(settings.worker_metrics_port)
    if settings.task_queue.lower() != "redis":
        raise RuntimeError("set AGENT_TASK_QUEUE=redis before starting the worker")
    queue = build_task_queue(settings)
    container = build_container(settings)
    await container.startup()
    try:
        while True:
            task = await queue.dequeue(timeout=5)
            if not task:
                continue
            task_repository = container.task_repository
            if task_repository is not None:
                await asyncio.to_thread(
                    task_repository.update,
                    task["task_id"],
                    status="running",
                    attempts=int(task.get("attempts", 0)) + 1,
                    error=None,
                )
            try:
                if task["task_name"] == "index_document":
                    payload = task["payload"]
                    document = await asyncio.to_thread(
                        container.document_repository.get,
                        payload["knowledge_base_id"],
                        payload["document_id"],
                    )
                    # 入队后文档可能已被用户删除，不能继续为已不存在的内容建立索引。
                    if document is None:
                        raise ValueError("document no longer exists")
                    await container.rag_service.index_document(document)
                else:
                    raise ValueError(f"unsupported task: {task['task_name']}")
            except Exception as exc:
                logger.exception("task_failed", extra={"task_id": task["task_id"]})
                task_status = await queue.retry(
                    task,
                    str(exc),
                    settings.task_max_attempts,
                    settings.task_retry_delay_seconds,
                )
                TASKS.labels(task["task_name"], task_status).inc()
                if task_repository is not None:
                    await asyncio.to_thread(
                        task_repository.update,
                        task["task_id"],
                        status=task_status,
                        error=str(exc),
                    )
            else:
                await queue.ack(task)
                TASKS.labels(task["task_name"], "succeeded").inc()
                if task_repository is not None:
                    await asyncio.to_thread(
                        task_repository.update,
                        task["task_id"],
                        status="succeeded",
                        error=None,
                    )
    finally:
        await container.shutdown()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(run())
