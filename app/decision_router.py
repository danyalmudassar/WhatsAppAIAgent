import asyncio
import time
from collections.abc import Callable, Sequence

from app.decision_backends import (
    BackendAuthError,
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    DecisionBackend,
)
from app.decision_models import DecisionErrorResponse, DecisionRequest, DecisionResponse


class DecisionRouter:
    def __init__(
        self,
        backends: Sequence[DecisionBackend],
        *,
        timeout_seconds: float,
        confidence_threshold: float,
        failure_threshold: int = 3,
        circuit_open_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.backends = list(backends)
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = confidence_threshold
        self.failure_threshold = failure_threshold
        self.circuit_open_seconds = circuit_open_seconds
        self.clock = clock
        self._failures: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}

    def _is_open(self, name: str) -> bool:
        return self._circuit_open_until.get(name, 0.0) > self.clock()

    def _record_failure(self, name: str) -> None:
        failures = self._failures.get(name, 0) + 1
        self._failures[name] = failures
        if failures >= self.failure_threshold:
            self._circuit_open_until[name] = self.clock() + self.circuit_open_seconds

    def _record_success(self, name: str) -> None:
        self._failures.pop(name, None)
        self._circuit_open_until.pop(name, None)

    def _apply_confidence(self, response: DecisionResponse) -> DecisionResponse:
        confidence = response.confidence
        if confidence is None:
            probabilities = [
                answer.probability
                for answer in response.answers.values()
                if answer.probability is not None
            ]
            confidence = min(probabilities) if probabilities else None
        if confidence is None or confidence < self.confidence_threshold:
            response.reason_code = "low_confidence"
            response.review_required = True
        else:
            response.confidence = confidence
        return response

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        started = self.clock()
        failures: list[str] = []
        for backend in self.backends:
            if self._is_open(backend.name):
                failures.append(f"{backend.name}: circuit open")
                continue
            try:
                response = await asyncio.wait_for(
                    backend.decide(request),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                self._record_failure(backend.name)
                failures.append(f"{backend.name}: timeout")
                continue
            except BackendAuthError:
                self._record_failure(backend.name)
                failures.append(f"{backend.name}: authentication failed")
                continue
            except (BackendTimeoutError, BackendUnavailableError, BackendProtocolError):
                self._record_failure(backend.name)
                failures.append(f"{backend.name}: unavailable")
                continue
            self._record_success(backend.name)
            response.latency_ms = max(response.latency_ms, (self.clock() - started) * 1000)
            return self._apply_confidence(response)

        return DecisionErrorResponse(
            answers={},
            confidence=None,
            backend=None,
            latency_ms=(self.clock() - started) * 1000,
            review_required=True,
            reason_code="all_backends_failed",
            error="; ".join(failures) or "No decision backends configured",
        )
