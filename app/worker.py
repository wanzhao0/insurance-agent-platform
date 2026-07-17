import asyncio

from app.bootstrap.container import build_container
from app.core.config import get_settings
from app.infrastructure.tasks.factory import build_task_queue


async def run() -> None:
    settings = get_settings()
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
            if task["task_name"] == "index_document":
                payload = task["payload"]
                document = container.document_repository.get(
                    payload["knowledge_base_id"], payload["document_id"]
                )
                if document is not None:
                    await container.rag_service.index_document(document)
    finally:
        await container.shutdown()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(run())
