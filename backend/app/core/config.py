"""Application settings — loaded from environment / .env via pydantic-settings."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    DOMAIN: str = "localhost"
    TZ: str = "Asia/Ho_Chi_Minh"

    # Dev-mode quick login: one-click sign-in as a fixed test account per role.
    # MUST be false in real production — when off, only whitelist login works.
    DEV_LOGIN_ENABLED: bool = False

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "labportal"
    POSTGRES_USER: str = "labportal"
    POSTGRES_PASSWORD: SecretStr = SecretStr("changeme_dev_password")
    DATABASE_URL: str = (
        "postgresql+asyncpg://labportal:changeme_dev_password@localhost:5432/labportal"
    )

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr = SecretStr("changeme_redis_password")
    REDIS_URL: str = "redis://:changeme_redis_password@localhost:6379/0"

    JWT_SECRET_KEY: SecretStr = SecretStr("dev_only_change_me_64_chars_minimum_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # bcse-id (id.bcse-vju.com) — federated SSO IdP for the BCSE ecosystem.
    # Replaces the abandoned Authentik experiment (ADR-0002 superseded).
    BCSE_ID_ISSUER: str = "https://id.bcse-vju.com"
    BCSE_ID_CLIENT_ID: str = "sv14-hardware-lab"
    BCSE_ID_CLIENT_SECRET: SecretStr = SecretStr("changeme_set_in_env")
    # Shared HS256 secret — MUST equal IDP_JWT_SECRET in bcse-id .env. Rotating
    # this on one side requires rotating on the other in the same window.
    BCSE_ID_JWT_SECRET: SecretStr = SecretStr("changeme_set_in_env")
    BCSE_ID_WEBHOOK_SECRET: SecretStr = SecretStr("changeme_set_in_env")
    # Base URL used to build redirect_uri + final user-facing redirects.
    BCSE_ID_APP_URL: str = "http://localhost:8000"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "lab-noreply@vju.edu.vn"
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = "lab-noreply@vju.edu.vn"
    SMTP_FROM_NAME: str = "VJU Lab Portal"
    # Comma-separated list of lecturer emails who get a notification when a
    # student submits a VPS-access proposal. Empty → no email (still creates
    # the in-portal access_request row, which the lecturer can see at
    # /admin/vps-access).
    LECTURER_NOTIFICATION_EMAIL: str = "buihuykien1311@gmail.com"

    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    BACKEND_SSH_KEY_PATH: str = "/app/ssh-keys/backend_admin_ed25519"
    BACKEND_SSH_KEY_PASSPHRASE: SecretStr = SecretStr("")
    DEVICE_KEY_ENCRYPTION_KEY: SecretStr = SecretStr("dev_only_32_chars_aes_xxxxxxxxxx")

    # SV14 itself — backend SSHs here to create/delete dynamic jump users
    # Backend container reaches SV14 host via Docker host-gateway (set in
    # docker-compose via extra_hosts). In dev / outside Docker, override to
    # the actual LAN IP `192.168.2.114`.
    SV14_HOST: str = "host.docker.internal"
    SV14_SSH_PORT: int = 22
    SV14_SSH_USER: str = "student"
    # Public-facing endpoint shown to users in the SSH command
    JUMP_HOST_PUBLIC: str = "ssh.bcse-vju.com"
    JUMP_HOST_PUBLIC_PORT: int = 2222
    # ADR-0013 (M5.8): jump host PAM hits /api/gateway/auth with this header.
    # Must match the value baked into /etc/vlab/gateway.env on the jump host.
    # Generate once with `openssl rand -hex 32` and pin in .env.prod.
    GATEWAY_SHARED_SECRET: SecretStr = SecretStr("dev_only_gateway_secret_change_me_32_hex_chars_xxxxxxxxxxxxxxxxxx")
    # Static SSH username users type at `ssh -J <user>@host`. Single account
    # on the jump host, no-shell, password-auth via PAM → backend.
    GATEWAY_SSH_USERNAME: str = "vlab"

    PLUG_API_TIMEOUT_SECONDS: int = 10
    PLUG_API_RETRY_COUNT: int = 3

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "json"

    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    RATE_LIMIT_API_PER_MINUTE: int = 100
    RATE_LIMIT_RESET_PER_MINUTE: int = 3
    RATE_LIMIT_UPLOAD_PER_HOUR: int = 10

    BOOKING_MAX_DURATION_HOURS: int = 8
    BOOKING_DEFAULT_QUOTA_HOURS_PER_WEEK: int = 10
    BOOKING_DEFAULT_MAX_CONCURRENT: int = 2
    BOOKING_DEFAULT_ADVANCE_DAYS: int = 7

    SESSION_PROVISION_RETRY_COUNT: int = 3
    SESSION_KEY_LIFETIME_BUFFER_MINUTES: int = 5
    SESSION_GRACE_PERIOD_MINUTES: int = 2

    DEVICE_POOL_CIDR: str = "192.168.20.0/24"
    PLUG_POOL_CIDR: str = "192.168.30.0/24"

    CORS_ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def is_prod(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
