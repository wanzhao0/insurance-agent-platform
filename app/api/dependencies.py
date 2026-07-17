import secrets

from fastapi import Header, HTTPException, Request, status

from app.domain.models import UserContext


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> UserContext:
    settings = request.app.state.container.settings
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token == "local-session" and settings.environment.lower() == "local":
            return UserContext(user_id="local-admin", username="admin", role="admin", tenant_ids=["*"])
        try:
            return request.app.state.container.auth_service.decode_token(token)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token") from exc
    if settings.environment.lower() == "local":
        return UserContext(user_id="local-admin", username="admin", role="admin", tenant_ids=["*"])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


def assert_tenant_access(user: UserContext, tenant_id: str) -> None:
    if user.role == "admin" or "*" in user.tenant_ids or tenant_id in user.tenant_ids:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant access denied")


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    settings = request.app.state.container.settings
    if settings.admin_token is not None:
        expected = settings.admin_token.get_secret_value()
        if x_admin_token is not None:
            if secrets.compare_digest(x_admin_token, expected):
                return
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
    if settings.environment.lower() == "local" and not authorization:
        return
    user = await get_current_user(request, authorization)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
