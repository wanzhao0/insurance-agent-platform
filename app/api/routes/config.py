from fastapi import APIRouter, Request

from fastapi import HTTPException, status

from app.domain.models import PublicConfigResponse, TenantConfigResponse


router = APIRouter()


@router.get("/public", response_model=PublicConfigResponse)
async def public_config(request: Request) -> PublicConfigResponse:
    return request.app.state.container.public_config()


@router.get("/tenants/{tenant_id}", response_model=TenantConfigResponse)
async def tenant_config(tenant_id: str, request: Request) -> TenantConfigResponse:
    config = request.app.state.container.knowledge_base_service.tenant_config(tenant_id)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return config
