from datetime import datetime, timedelta, timezone
import secrets

import jwt

from app.core.config import Settings
from app.domain.models import UserContext


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def login(self, username: str, password: str) -> UserContext | None:
        if not secrets.compare_digest(username, self.settings.local_admin_username):
            return None
        expected = self.settings.local_admin_password.get_secret_value()
        if not secrets.compare_digest(password, expected):
            return None
        return UserContext(
            user_id="local-admin",
            username=username,
            role="admin",
            tenant_ids=["*"],
        )

    def issue_token(self, user: UserContext) -> tuple[str, int]:
        if self.settings.jwt_secret is None:
            raise RuntimeError("AGENT_JWT_SECRET is required outside local mode")
        expires_in = self.settings.jwt_access_token_minutes * 60
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role,
            "tenant_ids": user.tenant_ids,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        }
        return jwt.encode(payload, self.settings.jwt_secret.get_secret_value(), algorithm=self.settings.jwt_algorithm), expires_in

    def decode_token(self, token: str) -> UserContext:
        if self.settings.jwt_secret is None:
            raise RuntimeError("AGENT_JWT_SECRET is not configured")
        payload = jwt.decode(
            token,
            self.settings.jwt_secret.get_secret_value(),
            algorithms=[self.settings.jwt_algorithm],
        )
        return UserContext(
            user_id=str(payload["sub"]),
            username=str(payload.get("username", payload["sub"])),
            role=payload.get("role", "viewer"),
            tenant_ids=list(payload.get("tenant_ids", [])),
        )
