from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "nemotron-3-nano:30b-cloud"
    ollama_api_key: SecretStr | None = None
    memory_path: Path = Path("data/memory.db")
    memory_key: SecretStr
    whatsapp_enabled: bool = False
    whatsapp_api_key: SecretStr | None = None
    whatsapp_endpoint: str = "https://api.whatsapp.com/agent/v1"
    whatsapp_auth_header: str = "Authorization"
    whatsapp_auth_scheme: str = "Bearer"
    whatsapp_poll_interval: float = 1.0
    response_language: Literal["roman_urdu"] = "roman_urdu"
    max_tool_seconds: float = 15.0
    max_response_chars: int = 3000
    workspace_root: Path = Path(".")
    port: int = 8000
    app_admin_token: SecretStr = SecretStr("local-dev-token")
    whatsapp_retry_base_seconds: float = 2.0
    whatsapp_retry_max_seconds: float = 60.0
    max_request_bytes: int = 1_048_576
    dashboard_origin: str = "http://localhost:3000"
    session_ttl_seconds: int = 86_400
    event_retention: int = 1_000
    owner_username: str = "admin"
    owner_password_hash: SecretStr = SecretStr("")
    decision_router_enabled: bool = False
    decision_backends: str = "laya,openjev,jev"
    decision_timeout_seconds: float = 2.0
    decision_confidence_threshold: float = 0.75
    laya_model: str = "convaiinnovations/laya-multilingual"
    openjev_url: str = ""
    jev_url: str = ""
    jev_api_key: SecretStr | None = None

    @field_validator("memory_key")
    @classmethod
    def require_memory_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("MEMORY_KEY must not be blank")
        return value

    @field_validator("app_admin_token")
    @classmethod
    def require_admin_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("APP_ADMIN_TOKEN must not be blank")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator("whatsapp_retry_base_seconds", "whatsapp_retry_max_seconds", "max_request_bytes")
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("production limits must be positive")
        return value

    @field_validator("session_ttl_seconds", "event_retention")
    @classmethod
    def validate_dashboard_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("dashboard limits must be positive")
        return value

    @field_validator("owner_username")
    @classmethod
    def validate_owner_username(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OWNER_USERNAME must not be blank")
        return value

    @field_validator("whatsapp_endpoint")
    @classmethod
    def validate_whatsapp_endpoint(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("WHATSAPP_ENDPOINT must be an HTTP(S) URL")
        return value

    @field_validator("decision_timeout_seconds")
    @classmethod
    def validate_decision_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("DECISION_TIMEOUT_SECONDS must be positive")
        return value

    @field_validator("decision_confidence_threshold")
    @classmethod
    def validate_decision_threshold(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("DECISION_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value
