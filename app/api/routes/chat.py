import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.request_context import get_request_id
from app.domain.models import ChatRequest


router = APIRouter()


def sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.post("/stream")
async def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    container = request.app.state.container
    try:
        context = container.chat_service.prepare(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    client_key = f"{payload.tenant_id}:{request.client.host if request.client else 'unknown'}"
    if not await container.rate_limiter.allow(client_key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")

    async def event_stream() -> AsyncIterator[str]:
        request_id = get_request_id()
        try:
            yield sse_event("start", {"request_id": request_id, "conversation_id": context.conversation_id})
            async with asyncio.timeout(container.settings.request_timeout_seconds):
                async for event in container.chat_service.stream(context):
                    yield sse_event(event.event, event.model_dump(mode="json"))
            yield sse_event("done", {"request_id": request_id})
        except TimeoutError:
            yield sse_event("error", {"code": "request_timeout", "message": "chat request timed out"})
        except Exception:
            container.logger.exception("chat_stream_failed", extra={"request_id": request_id})
            yield sse_event("error", {"code": "internal_error", "message": "chat request failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Request-ID": get_request_id()},
    )
