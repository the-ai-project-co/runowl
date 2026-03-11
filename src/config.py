"""Application configuration loaded from environment variables."""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Tier(StrEnum):
    FREE = "free"
    TEAM = "team"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class Env(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Gemini
    gemini_api_key: str = Field(..., description="Google Gemini API key")

    # Anthropic (test generation agent)
    anthropic_api_key: str | None = Field(None, description="Anthropic API key for test generation")

    # GitHub
    github_token: str | None = Field(None, description="GitHub personal access token")
    github_app_id: str | None = Field(None)
    github_app_private_key_path: str | None = Field(None)
    github_webhook_secret: str | None = Field(None)

    # RunOwl
    runowl_api_key: str | None = Field(None)
    runowl_tier: Tier = Field(Tier.FREE, description="Subscription tier")

    # Server
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    env: Env = Field(Env.DEVELOPMENT)


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
