from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: SecretStr = Field(
        ...,
        description="SQLAlchemy database URL for the backend database.",
    )
    application_name: str = "StartupReach AI"
    application_version: str = "0.1.0"
    environment: str = "development"
    api_token: SecretStr | None = Field(
        default=None,
        description="Bearer token for the protected single-user API.",
        validation_alias="STARTUPREACH_API_TOKEN",
    )
    cors_allowed_origins: str = "http://localhost:5173"
    tavily_api_key: SecretStr | None = Field(
        default=None,
        description="Server-side Tavily Search API key.",
    )
    tavily_timeout_seconds: float = Field(default=15.0, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    rate_limit_max_requests: int = Field(default=10, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a URL using the psycopg SQLAlchemy dialect."""
        url = self.database_url.get_secret_value()
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
