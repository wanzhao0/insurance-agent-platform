import asyncio

from fastapi import APIRouter, Depends, Request

from fastapi import HTTPException, status

from app.api.dependencies import assert_tenant_access, get_current_user
from app.domain.models import PublicConfigResponse, TenantConfigResponse
from app.domain.models import UserContext


router = APIRouter()


@router.get("/public", response_model=PublicConfigResponse)
async def public_config(request: Request) -> PublicConfigResponse:
    return request.app.state.container.public_config()


@router.get("/tenants/{tenant_id}", response_model=TenantConfigResponse)
async def tenant_config(
    tenant_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> TenantConfigResponse:
    assert_tenant_access(user, tenant_id)
    config = await asyncio.to_thread(
        request.app.state.container.knowledge_base_service.tenant_config,
        tenant_id,
    )
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return config
