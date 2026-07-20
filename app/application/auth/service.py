"""账号、密码和访问令牌的应用服务。"""

from datetime import datetime, timedelta, timezone
import base64
import binascii
import hashlib
import os
import secrets

import jwt

from app.core.config import Settings
from app.domain.models import UserContext, UserCreate, UserResponse, UserUpdate


class AuthService:
    """把用户仓库与 JWT/本地开发令牌组合成统一认证逻辑。"""

    def __init__(self, settings: Settings, user_repository=None) -> None:
        self.settings = settings
        self.user_repository = user_repository
        self.local_tokens: dict[str, UserContext] = {}

    @staticmethod
    def hash_password(password: str) -> str:
        """使用带随机 salt 的 scrypt 保存密码摘要，数据库不保存明文密码。"""
        salt = os.urandom(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded.split("$", 5)
            if algorithm != "scrypt":
                return False
            digest = hashlib.scrypt(
                password.encode(),
                salt=base64.b64decode(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=32,
            )
            return secrets.compare_digest(base64.b64encode(digest).decode(), expected)
        except (ValueError, TypeError, binascii.Error, OverflowError):
            return False

    def ensure_default_admin(self) -> None:
        if self.user_repository is None:
            return
        if self.user_repository.get_by_username(self.settings.local_admin_username) is None:
            self.user_repository.create(
                self.settings.local_admin_username,
                self.hash_password(self.settings.local_admin_password.get_secret_value()),
                "admin",
                ["*"],
                user_id="local-admin",
            )

    def login(self, username: str, password: str) -> UserContext | None:
        if self.user_repository is not None:
            stored = self.user_repository.get_by_username(username)
            if stored is None:
                return None
            user, password_hash = stored
            if not user.enabled or not self.verify_password(password, password_hash):
                return None
            return UserContext(
                user_id=user.user_id,
                username=user.username,
                role=user.role,
                tenant_ids=user.tenant_ids,
            )
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

    def list_users(self) -> list[UserResponse]:
        return self.user_repository.list() if self.user_repository is not None else []

    def resolve_user_context(self, token_user: UserContext) -> UserContext | None:
        """以数据库中的最新用户状态覆盖令牌中的旧角色和租户范围。

        因此停用账号或收回租户权限后，不必等待旧 JWT 自然过期。
        """
        if self.user_repository is None:
            return token_user
        user = self.user_repository.get_by_id(token_user.user_id)
        if user is None or not user.enabled:
            return None
        return UserContext(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            tenant_ids=user.tenant_ids,
        )

    def create_user(self, payload: UserCreate) -> UserResponse:
        if self.user_repository is None:
            raise ValueError("user persistence is not configured")
        if self.user_repository.get_by_username(payload.username) is not None:
            raise ValueError("username already exists")
        return self.user_repository.create(
            payload.username,
            self.hash_password(payload.password),
            payload.role,
            payload.tenant_ids,
        )

    def update_user(self, user_id: str, payload: UserUpdate) -> UserResponse:
        if self.user_repository is None:
            raise ValueError("user persistence is not configured")
        values = payload.model_dump(exclude_unset=True, exclude={"password", "tenant_ids"})
        if payload.password is not None:
            values["password_hash"] = self.hash_password(payload.password)
        user = self.user_repository.update(user_id, values, payload.tenant_ids)
        if user is None:
            raise ValueError("user not found")
        return user

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
        return jwt.encode(
            payload,
            self.settings.jwt_secret.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
        ), expires_in

    def issue_local_token(self, user: UserContext) -> tuple[str, int]:
        token = f"local-{secrets.token_urlsafe(32)}"
        self.local_tokens[token] = user
        return token, 86400

    def decode_local_token(self, token: str) -> UserContext | None:
        user = self.local_tokens.get(token)
        return self.resolve_user_context(user) if user else None

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
