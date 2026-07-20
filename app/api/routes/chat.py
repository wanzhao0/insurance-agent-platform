"""聊天 SSE 接口。

路由只处理 HTTP 层的鉴权、限流和流式响应；检索、工具调用、模型调用均由
``ChatService`` 及其工作流完成。
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.request_context import get_request_id
from app.core.metrics import CHAT_TURNS, TOOL_CALLS
from app.api.dependencies import assert_tenant_access, get_current_user
from app.domain.models import ChatRequest, UserContext


router = APIRouter()


def sse_event(event: str, payload: dict) -> str:
    """把内部事件编码为浏览器可持续接收的 Server-Sent Events 帧。"""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """在租户权限和限流通过后，持续输出 Agent 事件直到完成或超时。"""
    container = request.app.state.container
    assert_tenant_access(user, payload.tenant_id)
    CHAT_TURNS.labels(payload.tenant_id).inc()
    try:
        context = await asyncio.to_thread(container.chat_service.prepare, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    client_key = f"{payload.tenant_id}:{request.client.host if request.client else 'unknown'}"
    if not await container.rate_limiter.allow(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
        )

    async def event_stream() -> AsyncIterator[str]:
        request_id = get_request_id()
        try:
            yield sse_event(
                "start", {"request_id": request_id, "conversation_id": context.conversation_id}
            )
            # 超时覆盖整条对话链路，包括模型流式输出和工具调用。
            async with asyncio.timeout(container.settings.request_timeout_seconds):
                async for event in container.chat_service.stream(context):
                    if event.event == "tool_call" and event.tool_name:
                        TOOL_CALLS.labels(event.tool_name).inc()
                    yield sse_event(event.event, event.model_dump(mode="json"))
            yield sse_event("done", {"request_id": request_id})
        except TimeoutError:
            yield sse_event(
                "error", {"code": "request_timeout", "message": "chat request timed out"}
            )
        except Exception:
            container.logger.exception("chat_stream_failed", extra={"request_id": request_id})
            yield sse_event("error", {"code": "internal_error", "message": "chat request failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": get_request_id(),
        },
    )
