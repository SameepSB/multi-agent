from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "development", "production"]
    log_level: str
    api_port: int | None = None
    weather_agent_url: str | None = None
    travel_agent_url: str | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    request_timeout_seconds: int = Field(ge=1, le=30)
    max_cities: int = Field(ge=2, le=4)
    local_api_token: SecretStr | None = None
    local_coordinator_token: SecretStr | None = None
    stub_providers: bool = False
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    weather_a2a_audience: str | None = None
    travel_a2a_audience: str | None = None
    trusted_coordinator_object_id: str | None = None
    managed_identity_client_id: str | None = None
    travel_data_path: str = "data/travel_data.json"
    nws_user_agent: str | None = Field(default=None, max_length=256)
    max_request_bytes: int = Field(default=32_768, ge=1024, le=65_536)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR")
        return value

    @field_validator("nws_user_agent")
    @classmethod
    def validate_nws_user_agent(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if any(ord(character) < 32 for character in value):
            raise ValueError("NWS_USER_AGENT must be non-empty and contain no control characters")
        return value

    def validate_for(self, service: Literal["api", "coordinator", "weather", "travel"]) -> None:
        if service == "coordinator":
            self._require("WEATHER_AGENT_URL", self.weather_agent_url)
            self._require("TRAVEL_AGENT_URL", self.travel_agent_url)
            if not self.stub_providers:
                self._require("OPENAI_API_KEY", self.openai_api_key)
            self._require("WEATHER_A2A_AUDIENCE", self.weather_a2a_audience)
            self._require("TRAVEL_A2A_AUDIENCE", self.travel_a2a_audience)
            if not self.stub_providers and self.openai_api_key.get_secret_value() == "replace-me":
                raise ValueError("Set OPENAI_API_KEY when STUB_PROVIDERS is disabled")
            if self.app_env == "local":
                self._require("LOCAL_COORDINATOR_TOKEN", self.local_coordinator_token)
            else:
                self._require("OIDC_ISSUER", self.oidc_issuer)
                self._require("OIDC_JWKS_URL", self.oidc_jwks_url)
                self._require("MANAGED_IDENTITY_CLIENT_ID", self.managed_identity_client_id)
        if service in {"api", "coordinator"}:
            if self.api_port is None:
                if self.app_env != "local":
                    raise ValueError("API_PORT is required outside local development")
                self.api_port = 8080
        if service == "api":
            if self.app_env == "local":
                self._require("LOCAL_API_TOKEN", self.local_api_token)
                self._require("LOCAL_COORDINATOR_TOKEN", self.local_coordinator_token)
            else:
                self._require("OIDC_ISSUER", self.oidc_issuer)
                self._require("OIDC_AUDIENCE", self.oidc_audience)
                self._require("OIDC_JWKS_URL", self.oidc_jwks_url)
        if service in {"weather", "travel"}:
            audience = (
                self.weather_a2a_audience if service == "weather" else self.travel_a2a_audience
            )
            self._require(f"{service.upper()}_A2A_AUDIENCE", audience)
            if service == "weather" and not self.stub_providers:
                self._require("NWS_USER_AGENT", self.nws_user_agent)
            if self.app_env == "local":
                self._require("LOCAL_COORDINATOR_TOKEN", self.local_coordinator_token)
            else:
                for name, value in (
                    ("OIDC_ISSUER", self.oidc_issuer),
                    ("OIDC_JWKS_URL", self.oidc_jwks_url),
                    ("TRUSTED_COORDINATOR_OBJECT_ID", self.trusted_coordinator_object_id),
                ):
                    self._require(name, value)
        if service == "api" and self.app_env == "local":
            if self.local_api_token and self.local_coordinator_token:
                if (
                    self.local_api_token.get_secret_value()
                    == self.local_coordinator_token.get_secret_value()
                ):
                    raise ValueError("API and worker local credentials must be distinct")
                if (
                    min(
                        len(self.local_api_token.get_secret_value()),
                        len(self.local_coordinator_token.get_secret_value()),
                    )
                    < 24
                ):
                    raise ValueError("Local credentials must contain at least 24 characters")

    @staticmethod
    def _require(name: str, value: object) -> None:
        if value is None or value == "":
            raise ValueError(f"{name} is required for this service")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
