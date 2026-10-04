"""Application settings. This is the ONLY module that reads environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    session_secret: SecretStr
    database_url: SecretStr  # Neon pooled connection, app role (runtime)
    database_url_direct: SecretStr  # Neon direct connection, owner role (Alembic migrations)
    # non-owner role the API connects as (RLS applies). Used in migration DDL, hence the pattern.
    db_app_role: str = Field(default="cocreat_app", pattern=r"^[a-z_][a-z0-9_]{0,62}$")
    db_pool_size: int = 5
    db_max_overflow: int = 5
    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_domain: str | None = None
    # Built frontend served by the API itself (single-origin hosting). Unset in local development.
    frontend_dir: str | None = None
    session_ttl_days: int = 30
    # Proxies in front of the API that append to X-Forwarded-For (Render: 1). The client IP is taken that many
    # entries from the RIGHT, so a client-supplied X-Forwarded-For can't spoof it. 0 = socket peer address.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    sms_api_key: SecretStr
    sms_sender_id: str
    sms_otp_template_id: str
    otp_dev_mode: bool = False  # True ONLY locally: accept fixed OTP 123456, send no SMS

    r2_account_id: str
    r2_access_key_id: SecretStr
    r2_secret_access_key: SecretStr
    r2_bucket: str

    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = 0.05
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self:
        if self.app_env == "production":
            if self.otp_dev_mode:
                raise ValueError("OTP_DEV_MODE must be false when APP_ENV=production")
            if len(self.session_secret.get_secret_value()) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters in production")
            if any(o.startswith("http://") for o in self.cors_origins):
                raise ValueError("CORS_ORIGINS must be https in production")
        return self

    @property
    def is_production_like(self) -> bool:
        return self.app_env in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
