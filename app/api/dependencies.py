"""FastAPI 路由共享的身份识别与授权依赖。"""

import secrets
import asyncio

from fastapi import Header, HTTPException, Request, status

from app.domain.models import UserContext


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> UserContext:
    """从 Bearer Token 解析用户，并从仓库刷新其当前的角色和租户范围。"""
    settings = request.app.state.container.settings
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token == "local-session" and settings.environment.lower() == "local":
            return UserContext(
                user_id="local-admin", username="admin", role="admin", tenant_ids=["*"]
            )
        if token.startswith("local-") and settings.environment.lower() == "local":
            user = await asyncio.to_thread(
                request.app.state.container.auth_service.decode_local_token,
                token,
            )
            if user is not None:
                return user
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid access token",
            )
        try:
            service = request.app.state.container.auth_service
            token_user = service.decode_token(token)
            user = await asyncio.to_thread(service.resolve_user_context, token_user)
            if user is None:
                raise ValueError("user is disabled or missing")
            return user
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token"
            ) from exc
    if settings.environment.lower() == "local":
        return UserContext(user_id="local-admin", username="admin", role="admin", tenant_ids=["*"])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


def assert_tenant_access(user: UserContext, tenant_id: str) -> None:
    """确保非管理员只能访问自己被显式授权的租户。"""
    if user.role == "admin" or "*" in user.tenant_ids or tenant_id in user.tenant_ids:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant access denied")


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> UserContext:
    """要求管理员权限；本地环境保留无令牌的开发捷径，生产环境不可依赖它。"""
    settings = request.app.state.container.settings
    if settings.admin_token is not None:
        expected = settings.admin_token.get_secret_value()
        if x_admin_token is not None:
            if secrets.compare_digest(x_admin_token, expected):
                return UserContext(
                    user_id="admin-token",
                    username="admin-token",
                    role="admin",
                    tenant_ids=["*"],
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
            )
    if settings.environment.lower() == "local" and not authorization:
        return UserContext(user_id="local-admin", username="admin", role="admin", tenant_ids=["*"])
    user = await get_current_user(request, authorization)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user
