from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_PREFIX = "dev-only"  # noqa: S105 - public prefix, not a credential


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RestroOS"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./restroos.db"

    jwt_secret: str = "dev-only-change-me-please-use-a-long-random-value"  # noqa: S105
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "restroos"
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    refresh_cookie_name: str = "restroos_refresh"

    auth_rate_limit_per_minute: int = 20
    password_min_length: int = 10
    password_max_length: int = 128

    free_plan_max_restaurants: int = 1
    free_plan_max_staff: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def _supported_algorithm(cls, value: str) -> str:
        # Phase 2 ships HS256. RS256 is a documented upgrade path; refusing unknown
        # algorithms prevents the classic "alg" confusion class of bugs.
        if value != "HS256":
            raise ValueError("Only HS256 is supported in this phase")
        return value

    @model_validator(mode="after")
    def _production_safety(self) -> Settings:
        if self.jwt_secret.startswith(DEV_SECRET_PREFIX):
            if self.environment == "production":
                raise ValueError("JWT_SECRET must be replaced in production")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")

        if self.environment == "production":
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("Production requires DATABASE_URL with postgresql+asyncpg")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
