import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.domain.models import ChatMessage, ModelCompletion, ModelToolCall, ToolDescriptor


class OpenAICompatibleModelClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.model_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.model_timeout_seconds),
        )

    def _headers(self) -> dict[str, str]:
        if self.settings.model_api_key is None:
            raise RuntimeError("AGENT_MODEL_API_KEY is required for the configured model provider")
        return {"Authorization": f"Bearer {self.settings.model_api_key.get_secret_value()}"}

    def _payload(
        self,
        messages: list[ChatMessage],
        stream: bool,
        temperature: float,
        tools: list[ToolDescriptor] | None = None,
    ) -> dict:
        payload = {
            "model": self.settings.model_name,
            "messages": [self._serialize_message(message) for message in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ]
        return payload

    @staticmethod
    def _serialize_message(message: ChatMessage) -> dict:
        if message.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.name,
                "content": message.content or "",
            }
        if message.role == "assistant" and message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        return {"role": message.role, "content": message.content or ""}

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        tools: list[ToolDescriptor] | None = None,
    ) -> ModelCompletion:
        last_error: Exception | None = None
        for attempt in range(self.settings.model_max_retries + 1):
            try:
                response = await self.client.post(
                    "/chat/completions",
                    headers=self._headers(),
                    json=self._payload(messages, False, temperature, tools),
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                tool_calls = []
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function", {})
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    tool_calls.append(
                        ModelToolCall(
                            call_id=tool_call.get("id", "unknown-call"),
                            name=function.get("name", ""),
                            arguments=arguments if isinstance(arguments, dict) else {},
                        )
                    )
                return ModelCompletion(content=message.get("content"), tool_calls=tool_calls)
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < self.settings.model_max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise RuntimeError("model completion failed") from last_error

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        async with self.client.stream(
            "POST",
            "/chat/completions",
            headers=self._headers(),
            json=self._payload(messages, True, temperature),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    content = chunk["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if content:
                    yield content

    async def healthcheck(self) -> None:
        if self.settings.model_api_key is None:
            raise RuntimeError("model API key is not configured")

    async def close(self) -> None:
        await self.client.aclose()
