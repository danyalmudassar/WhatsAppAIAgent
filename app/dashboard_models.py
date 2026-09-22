from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, SecretStr, field_validator


class ProviderType(StrEnum):
    ollama = "ollama"
    openai_compatible = "openai_compatible"


class ProviderConfig(BaseModel):
    id: str
    type: ProviderType
    name: str
    base_url: str
    model: str
    enabled: bool = True
    priority: int = Field(default=0, ge=0)
    has_secret: bool = False
    secret_last_four: str | None = None
    revision: int = 1

    @field_validator("name", "base_url", "model")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ProviderSecret(BaseModel):
    secret: SecretStr


class AgentConfig(BaseModel):
    id: str
    name: str
    system_prompt: str = ""
    response_language: str = "roman_urdu"
    memory_profile: str = "default"
    tools: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    revision: int = 1

    @field_validator("name")
    @classmethod
    def required_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent name must not be blank")
        return value


class SessionRecord(BaseModel):
    id: str
    actor: str
    role: str = "owner"
    expires_at: datetime
    revoked: bool = False


class RuntimeEvent(BaseModel):
    id: str
    timestamp: datetime
    type: str
    severity: str = "info"
    correlation_id: str
    agent_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    id: str
    timestamp: datetime
    actor: str
    action: str
    resource: str
    revision: int | None = None
    result: str
