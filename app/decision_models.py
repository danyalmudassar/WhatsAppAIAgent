from typing import Any, Literal

from pydantic import BaseModel, Field


QuestionType = Literal["choice", "score", "noul", "boolean", "number", "text"]
BackendName = Literal["laya", "openjev", "jev", "mock"]
DecisionReasonCode = Literal[
    "ok",
    "low_confidence",
    "backend_unavailable",
    "backend_timeout",
    "backend_auth_failed",
    "invalid_request",
    "all_backends_failed",
]


class TypedQuestion(BaseModel):
    type: QuestionType
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] | list[str] | None = None


class DecisionRequest(BaseModel):
    state: dict[str, Any] | str
    questions: dict[str, TypedQuestion] = Field(min_length=1)
    threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class DecisionAnswer(BaseModel):
    value: Any
    probability: float | None = Field(default=None, ge=0.0, le=1.0)


class DecisionResponse(BaseModel):
    answers: dict[str, DecisionAnswer]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    backend: BackendName | None
    latency_ms: float = Field(ge=0.0)
    review_required: bool
    reason_code: DecisionReasonCode


class DecisionErrorResponse(DecisionResponse):
    answers: dict[str, DecisionAnswer] = Field(default_factory=dict)
    error: str = Field(min_length=1)
