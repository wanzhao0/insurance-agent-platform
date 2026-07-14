import asyncio
import re
from collections.abc import AsyncIterator

from app.domain.models import ChatMessage


class MockModelClient:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.2) -> str:
        chunks: list[str] = []
        async for chunk in self.stream(messages, temperature=temperature):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(self, messages: list[ChatMessage], *, temperature: float = 0.2) -> AsyncIterator[str]:
        user_message = next(message.content for message in reversed(messages) if message.role == "user")
        answer = self._grounded_answer(user_message, messages)
        for index in range(0, len(answer), 12):
            await asyncio.sleep(0.015)
            yield answer[index : index + 12]

    @staticmethod
    def _grounded_answer(user_message: str, messages: list[ChatMessage]) -> str:
        context_message = next(
            (message.content for message in messages if message.content.startswith("知识库上下文（仅供参考）：")),
            None,
        )
        if context_message is None:
            return (
                f"当前知识库没有检索到与“{user_message}”直接相关的内容。"
                "我无法据此确认具体条款，建议补充保单或案件信息后转人工复核。"
            )

        context = context_message.split("：\n", 1)[-1]
        blocks = re.split(r"\n\n(?=\[\d+\] )", context)
        grounded_parts: list[str] = []
        for block in blocks[:3]:
            lines = block.splitlines()
            if len(lines) < 2:
                continue
            citation = lines[0]
            body = MockModelClient._relevant_section("\n".join(lines[1:]), user_message)
            if body:
                grounded_parts.append(f"{citation}\n{body}")
        if not grounded_parts:
            grounded_parts.append(context[:1200])
        return (
            "根据当前知识库，与你的问题相关的信息如下：\n\n"
            + "\n\n".join(grounded_parts)
            + "\n\n以上内容来自当前知识库；具体承保、金额、时限或合同结论仍以保单条款和人工审核结果为准。"
        )

    @staticmethod
    def _relevant_section(content: str, user_message: str) -> str:
        headings = list(re.finditer(r"(?m)^##\s+(.+)$", content))
        query_keywords = [keyword for keyword in ("流程", "材料", "边界", "时限", "责任") if keyword in user_message]
        for index, heading in enumerate(headings):
            title = heading.group(1)
            if query_keywords and any(keyword in title for keyword in query_keywords):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
                return content[heading.start() : end].strip()
        return content.strip()[:1200]

    async def healthcheck(self) -> None:
        return None
