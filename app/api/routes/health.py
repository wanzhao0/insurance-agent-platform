from fastapi import APIRouter, Request

from app.domain.models import HealthResponse


router = APIRouter()


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service="insurance-agent-platform")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse:
    await request.app.state.container.healthcheck()
    return HealthResponse(status="ok", service="insurance-agent-platform")
