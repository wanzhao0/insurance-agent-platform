from fastapi import APIRouter, Request

from app.domain.models import ToolDescriptor


router = APIRouter()


@router.get("", response_model=list[ToolDescriptor])
async def list_tools(request: Request) -> list[ToolDescriptor]:
    return request.app.state.container.tool_registry.describe()
