import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.domain.models import LoginRequest, TokenResponse, UserContext


router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    service = request.app.state.container.auth_service
    user = await asyncio.to_thread(service.login, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if request.app.state.container.settings.jwt_secret is None:
        if request.app.state.container.settings.environment.lower() != "local":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="auth is not configured"
            )
        if user.user_id == "local-admin":
            return TokenResponse(access_token="local-session", expires_in=86400, user=user)
        token, expires_in = service.issue_local_token(user)
        return TokenResponse(access_token=token, expires_in=expires_in, user=user)
    token, expires_in = service.issue_token(user)
    return TokenResponse(access_token=token, expires_in=expires_in, user=user)


@router.get("/me", response_model=UserContext)
async def current_user(user: UserContext = Depends(get_current_user)) -> UserContext:
    return user
