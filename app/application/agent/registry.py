from typing import Any

from app.domain.models import ToolDescriptor
from app.domain.ports import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.descriptor.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[ToolDescriptor]:
        return [self._tools[name].descriptor for name in self.names()]

    async def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"tool is not registered: {name}")
        return await tool.invoke(arguments)
