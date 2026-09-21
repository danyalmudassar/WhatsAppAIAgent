from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    message_id: str
    sender_id: str
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: Literal["local", "whatsapp"] = "local"
    raw_id: str | None = None


class OutgoingMessage(BaseModel):
    message_id: str
    text: str
    recipient_id: str | None = None
    requires_confirmation: bool = False
    citations: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    ok: bool
    content: str
    requires_confirmation: bool = False
    error_code: str | None = None


class AgentState(TypedDict):
    message: IncomingMessage
    history: list[dict[str, str]]
    memory_context: dict[str, object]
    route: str
    tool_results: list[ToolResult]
    response: OutgoingMessage | None
