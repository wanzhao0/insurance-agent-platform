import secrets

from fastapi import Header, HTTPException, Request, status


async def require_admin(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    settings = request.app.state.container.settings
    if settings.admin_token is None:
        if settings.environment.lower() == "local":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin access is not configured",
        )
    expected = settings.admin_token.get_secret_value()
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
