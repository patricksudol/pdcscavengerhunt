from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PDC_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./pdcscavengerhunt.db"
    public_base_url: str = "http://localhost:8000"
    session_secret: str = "development-session-secret"
    clue_code_secret: str = "development-clue-code-secret"
    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_admin_name: str = "Game Administrator"
    frontend_dist: str = "frontend/dist"
    secure_cookies: bool = False
    session_max_age_seconds: int = 8 * 60 * 60
    login_rate_limit: int = 5
    code_rate_limit: int = 20
    rate_limit_window_seconds: int = 15 * 60
    photo_max_bytes: int = 8 * 1024 * 1024
    video_max_bytes: int = 100 * 1024 * 1024
    video_max_duration_seconds: int = 5 * 60
    media_upload_url_ttl_seconds: int = 15 * 60
    media_read_url_ttl_seconds: int = 5 * 60
    cloudflare_media_enabled: bool = False
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_r2_access_key_id: str = ""
    cloudflare_r2_secret_access_key: str = ""
    cloudflare_r2_bucket: str = ""
    cloudflare_stream_customer_subdomain: str = ""
    cloudflare_stream_webhook_secret: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @field_validator("public_base_url")
    @classmethod
    def normalize_public_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cloudflare_stream_customer_subdomain")
    @classmethod
    def normalize_stream_customer_subdomain(cls, value: str) -> str:
        normalized = value.removeprefix("https://").removeprefix("http://").rstrip("/")
        if normalized and "." not in normalized:
            normalized = f"customer-{normalized}.cloudflarestream.com"
        return normalized

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if self.environment != "production":
            return self
        errors: list[str] = []
        if not self.database_url.startswith("postgresql+psycopg://"):
            errors.append("PDC_DATABASE_URL must use PostgreSQL in production")
        public_origin = urlsplit(self.public_base_url)
        if (
            public_origin.scheme != "https"
            or not public_origin.netloc
            or public_origin.path
            or public_origin.query
            or public_origin.fragment
        ):
            errors.append(
                "PDC_PUBLIC_BASE_URL must be an HTTPS origin without a path, query, or fragment"
            )
        if not self.secure_cookies:
            errors.append("PDC_SECURE_COOKIES must be true in production")
        if len(self.session_secret) < 32 or self.session_secret.startswith("development-"):
            errors.append("PDC_SESSION_SECRET must be a unique value of at least 32 characters")
        if len(self.clue_code_secret) < 32 or self.clue_code_secret.startswith("development-"):
            errors.append("PDC_CLUE_CODE_SECRET must be a unique value of at least 32 characters")
        if bool(self.seed_admin_email) != bool(self.seed_admin_password):
            errors.append(
                "PDC_SEED_ADMIN_EMAIL and PDC_SEED_ADMIN_PASSWORD must be set together"
            )
        if self.seed_admin_password and len(self.seed_admin_password) < 12:
            errors.append("PDC_SEED_ADMIN_PASSWORD must be at least 12 characters")
        if self.seed_admin_email and not self.seed_admin_name.strip():
            errors.append("PDC_SEED_ADMIN_NAME must not be blank")
        if self.cloudflare_media_enabled:
            cloudflare_values = {
                "PDC_CLOUDFLARE_ACCOUNT_ID": self.cloudflare_account_id,
                "PDC_CLOUDFLARE_API_TOKEN": self.cloudflare_api_token,
                "PDC_CLOUDFLARE_R2_ACCESS_KEY_ID": self.cloudflare_r2_access_key_id,
                "PDC_CLOUDFLARE_R2_SECRET_ACCESS_KEY": (
                    self.cloudflare_r2_secret_access_key
                ),
                "PDC_CLOUDFLARE_R2_BUCKET": self.cloudflare_r2_bucket,
                "PDC_CLOUDFLARE_STREAM_CUSTOMER_SUBDOMAIN": (
                    self.cloudflare_stream_customer_subdomain
                ),
            }
            missing = [name for name, value in cloudflare_values.items() if not value]
            if missing:
                errors.append(f"Cloudflare media requires {', '.join(missing)}")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+aiosqlite", "")

    @property
    def public_hostname(self) -> str:
        return urlsplit(self.public_base_url).hostname or "localhost"


@lru_cache
def get_settings() -> Settings:
    return Settings()
