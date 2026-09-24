import asyncio
import time
from typing import Any, Literal, Protocol

import httpx

from app.decision_models import (
    DecisionAnswer,
    DecisionRequest,
    DecisionResponse,
)


class DecisionBackend(Protocol):
    name: Literal["laya", "openjev", "jev"]

    async def decide(self, request: DecisionRequest) -> DecisionResponse: ...


class BackendUnavailableError(RuntimeError):
    pass


class BackendTimeoutError(RuntimeError):
    pass


class BackendAuthError(RuntimeError):
    pass


class BackendProtocolError(RuntimeError):
    pass


def _normalize_answers(raw_answers: Any) -> dict[str, DecisionAnswer]:
    if not isinstance(raw_answers, dict) or not raw_answers:
        raise ValueError("decision response must contain non-empty answers")

    normalized: dict[str, DecisionAnswer] = {}
    for key, raw in raw_answers.items():
        if not isinstance(raw, dict):
            normalized[key] = DecisionAnswer(value=raw)
            continue
        value = raw.get("value")
        if value is None:
            for candidate in ("choice", "score", "noul", "boolean", "number", "text"):
                if candidate in raw:
                    value = raw[candidate]
                    break
        if value is None:
            raise ValueError(f"decision answer {key!r} has no value")
        normalized[key] = DecisionAnswer(value=value, probability=raw.get("probability"))
    return normalized


def _normalize_result(
    payload: Any,
    backend: Literal["laya", "openjev", "jev"],
    started: float,
) -> DecisionResponse:
    if not isinstance(payload, dict):
        raise BackendProtocolError("decision backend returned a non-object response")
    try:
        answers = _normalize_answers(payload.get("answers"))
        confidence = payload.get("confidence")
        if confidence is None:
            probabilities = [
                answer.probability
                for answer in answers.values()
                if answer.probability is not None
            ]
            confidence = min(probabilities) if probabilities else None
        return DecisionResponse(
            answers=answers,
            confidence=confidence,
            backend=backend,
            latency_ms=(time.monotonic() - started) * 1000,
            review_required=False,
            reason_code="ok",
        )
    except (TypeError, ValueError) as exc:
        raise BackendProtocolError(str(exc)) from exc


class _HttpDecisionBackend:
    name: Literal["openjev", "jev"]

    def __init__(
        self,
        base_url: str,
        timeout: float,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.transport = transport

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/decide",
                    headers=headers,
                    json=request.model_dump(mode="json"),
                )
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError("decision backend timed out") from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError("decision backend unavailable") from exc

        if response.status_code in {401, 403}:
            raise BackendAuthError("decision backend authentication failed")
        if response.status_code in {408, 504}:
            raise BackendTimeoutError("decision backend timed out")
        if response.status_code >= 500:
            raise BackendUnavailableError("decision backend unavailable")
        if response.status_code >= 400:
            raise BackendProtocolError("decision backend rejected the request")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendProtocolError("decision backend returned invalid JSON") from exc
        return _normalize_result(payload, self.name, started)


class OpenJevBackend(_HttpDecisionBackend):
    name: Literal["openjev"] = "openjev"


class JevBackend(_HttpDecisionBackend):
    name: Literal["jev"] = "jev"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(base_url, timeout, api_key=api_key, transport=transport)


class LayaBackend:
    name: Literal["laya"] = "laya"

    def __init__(self, model_name: str, timeout: float = 2.0, agent: Any | None = None):
        self.model_name = model_name
        self.timeout = timeout
        self._agent = agent

    def _load(self) -> Any:
        if self._agent is None:
            try:
                import laya
            except ImportError as exc:
                raise BackendUnavailableError("Laya package is not installed") from exc
            self._agent = laya.load(self.model_name)
        return self._agent

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        started = time.monotonic()
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._load().predict,
                    request.state,
                    {
                        key: question.model_dump(mode="json")
                        for key, question in request.questions.items()
                    },
                ),
                timeout=self.timeout,
            )
        except TimeoutError as exc:
            raise BackendTimeoutError("Laya decision timed out") from exc
        except BackendUnavailableError:
            raise
        except Exception as exc:
            raise BackendProtocolError("Laya decision failed") from exc
        return _normalize_result(payload, self.name, started)
