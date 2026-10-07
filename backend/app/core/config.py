"""Application configuration.

All configuration is environment driven (12-factor).  Nothing secret is ever
committed: ``.env`` files are git-ignored and ``.env.example`` documents the
supported variables.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings for the Kayan ERP backend."""

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    app_name: str = "Kayan ERP"
    app_version: str = "1.0.0"
    environment: str = Field(default="development", description="development|test|production")
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    root_path: str = ""

    # -------------------------------------------------------------- database
    database_url: str = "sqlite:///./kayan_dev.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ------------------------------------------------------------------ auth
    secret_key: str = "insecure-development-secret-change-me"  # noqa: S105 - dev default, validated
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    password_reset_expire_minutes: int = 45
    password_min_length: int = 8
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    bcrypt_rounds: int = 12

    # ------------------------------------------------------------- rate limit
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 600
    login_rate_limit_per_minute: int = 20

    # ------------------------------------------------------------------ cors
    cors_origins: str = "*"
    cors_allow_credentials: bool = True

    # --------------------------------------------------------------- storage
    storage_dir: str = str(BASE_DIR / "storage")
    max_upload_size_mb: int = 25
    allowed_upload_extensions: str = "pdf,jpg,jpeg,png,gif,webp,xlsx,xls,csv,doc,docx,txt,zip"

    # ---------------------------------------------------------------- backup
    backup_dir: str = str(BASE_DIR / "backups")
    backup_retention_days: int = 14
    backup_schedule_cron: str = "0 2 * * *"

    # ------------------------------------------------------------- bootstrap
    seed_demo_data: bool = False
    bootstrap_admin_email: str = "admin@kayan.local"
    bootstrap_admin_password: str = "Admin@12345"  # noqa: S105 - dev default, rotatable

    # -------------------------------------------------------------- business
    default_currency_code: str = "EGP"
    default_country_code: str = "EG"
    default_timezone: str = "Africa/Cairo"
    fiscal_year_start_month: int = 1

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        allowed = {"development", "test", "production", "staging"}
        if value.lower() not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return value.lower()

    # ------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {ext.strip().lower().lstrip(".") for ext in self.allowed_upload_extensions.split(",") if ext.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        path = Path(self.storage_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def backup_path(self) -> Path:
        path = Path(self.backup_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def validate_production(self) -> None:
        """Refuse to boot in production with development defaults."""
        problems: list[str] = []
        if self.is_production:
            if self.secret_key == "insecure-development-secret-change-me" or len(self.secret_key) < 32:  # noqa: S105
                problems.append("SECRET_KEY must be set to a strong value (>=32 chars) in production")
            if self.debug:
                problems.append("DEBUG must be false in production")
            if self.is_sqlite:
                problems.append("DATABASE_URL must point to PostgreSQL in production")
            if "*" in self.cors_origin_list:
                problems.append("CORS_ORIGINS must list explicit origins in production")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if os.environ.get("KAYAN_VALIDATE_PROD") == "1":
        settings.validate_production()
    return settings


settings = get_settings()
