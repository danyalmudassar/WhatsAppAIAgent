# System One Decision Router Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested decision-router sidecar/interface that can use Laya, OpenJev, or optional remote Jev for typed decisions while preserving the existing Ollama/LangGraph conversational path.

**Architecture:** Keep the current FastAPI application and LangGraph graph as the orchestration and prose-generation layer. Add a provider-neutral decision contract, backend adapters, and an HTTP router with explicit fallback states; expose the same contract through MCP and documented HTTP examples for coding agents. Local Laya/OpenJev dependencies remain isolated from the production runtime until their smoke tests pass.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, LangGraph, pytest, Laya, OpenJev-compatible HTTP, optional Jev HTTP/SDK, MCP-compatible tool server, OpenAPI.

---

## File map and boundaries

- Create `app/decision_models.py`: Pydantic request/response/error models for typed decisions.
- Create `app/decision_backends.py`: backend protocol plus Laya, OpenJev, and Jev adapters.
- Create `app/decision_router.py`: ordered fallback, timeout, circuit-breaker state, confidence thresholds, and safe reason codes.
- Modify `app/config.py`: decision-router feature flags, endpoint URLs, credentials, timeouts, thresholds, and backend order.
- Modify `app/api.py`: authenticated `POST /decide` endpoint and health/status exposure without leaking secrets.
- Modify `app/graph.py`: optional decision step for intent, urgency, escalation, tool selection, and language hint; preserve existing behavior when unavailable.
- Modify `app/dashboard_models.py`, `app/dashboard_services.py`, and `app/dashboard_store.py` only if the existing provider model needs a decision-backend entry; do not store raw model secrets outside the existing encrypted secret store.
- Create `app/mcp_decision_server.py`: MCP tools backed by the same `DecisionRouter` contract.
- Create `tests/test_decision_models.py`, `tests/test_decision_backends.py`, `tests/test_decision_router.py`, `tests/test_decision_api.py`, and `tests/test_mcp_decision_server.py`.
- Create `scripts/test_laya.py`, `scripts/test_openjev.py`, and `scripts/benchmark_decisions.py` for isolated smoke tests and clearly labeled local/mock/live output.
- Modify `pyproject.toml`, `.env.example`, `README.md`, and `docs/DEPLOYMENT.md` for optional dependencies, configuration, usage, and deployment safety.
- Create `docs/superpowers/reports/2026-09-24-system-one-decision-router-validation.md` only after tests and smoke tests have run; this is a validation artifact, not a planning document.

### Task 1: Lock the typed decision contract

**Files:**
- Create: `app/decision_models.py`
- Test: `tests/test_decision_models.py`

- [ ] **Step 1: Write failing model tests**

Add tests covering a valid request, typed questions, backend status, per-answer probability, review signals, and explicit error states:

```python
def test_decision_request_accepts_json_state_and_typed_questions():
    request = DecisionRequest(
        state={"body": "charged twice"},
        questions={
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {"billing": "payments", "technical": "bugs"},
            }
        },
    )
    assert request.state["body"] == "charged twice"
    assert request.questions["department"].type == "choice"


def test_decision_response_preserves_backend_latency_and_review_signal():
    response = DecisionResponse(
        answers={"department": {"value": "billing", "probability": 0.94}},
        confidence=0.94,
        backend="laya",
        latency_ms=31.2,
        review_required=False,
        reason_code="ok",
    )
    assert response.backend == "laya"
    assert response.answers["department"].probability == 0.94


def test_decision_error_distinguishes_timeout_from_unavailable():
    error = DecisionErrorResponse(
        answers={},
        confidence=None,
        backend=None,
        latency_ms=1000,
        review_required=True,
        reason_code="backend_timeout",
        error="Decision backend timed out",
    )
    assert error.reason_code == "backend_timeout"
    assert error.review_required is True
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
.venv/bin/pytest -q tests/test_decision_models.py
```

Expected: collection/import failure because `app.decision_models` does not exist.

- [ ] **Step 3: Implement the contract**

Define strict Pydantic models with:

```python
class TypedQuestion(BaseModel):
    type: Literal["choice", "score", "noul", "boolean", "number", "text"]
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
    backend: Literal["laya", "openjev", "jev", "mock"] | None
    latency_ms: float = Field(ge=0.0)
    review_required: bool
    reason_code: Literal[
        "ok",
        "low_confidence",
        "backend_unavailable",
        "backend_timeout",
        "backend_auth_failed",
        "invalid_request",
        "all_backends_failed",
    ]


class DecisionErrorResponse(DecisionResponse):
    answers: dict[str, DecisionAnswer] = {}
    error: str
```

Use `Field(default_factory=dict)` rather than a mutable literal for production code. Keep error messages safe and never include provider credentials.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/test_decision_models.py
```

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/decision_models.py tests/test_decision_models.py
git commit -m "feat: define typed decision contract"
```

### Task 2: Add backend interfaces and adapters

**Files:**
- Create: `app/decision_backends.py`
- Modify: `app/config.py`
- Test: `tests/test_decision_backends.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing backend contract tests**

Use `httpx.MockTransport` for HTTP adapters and a fake Laya object. Tests must assert normalized output and safe error classification:

```python
@pytest.mark.asyncio
async def test_openjev_adapter_normalizes_typed_response():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "answers": {"department": {"choice": "billing", "probability": 0.91}},
                "confidence": 0.91,
            },
        )
    )
    backend = OpenJevBackend("http://openjev.test", timeout=1, transport=transport)
    result = await backend.decide(valid_request())
    assert result.answers["department"].value == "billing"
    assert result.backend == "openjev"


@pytest.mark.asyncio
async def test_jev_adapter_returns_auth_failure_without_exposing_key():
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    backend = JevBackend("https://jev.test", "secret-value", timeout=1, transport=transport)
    with pytest.raises(BackendAuthError) as exc_info:
        await backend.decide(valid_request())
    assert "secret-value" not in str(exc_info.value)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_decision_backends.py
```

Expected: import failure for the backend classes.

- [ ] **Step 3: Implement the backend protocol and normalized exceptions**

Implement:

```python
class DecisionBackend(Protocol):
    name: Literal["laya", "openjev", "jev"]

    async def decide(self, request: DecisionRequest) -> DecisionResponse: ...


class BackendUnavailableError(RuntimeError): ...
class BackendTimeoutError(RuntimeError): ...
class BackendAuthError(RuntimeError): ...
class BackendProtocolError(RuntimeError): ...
```

Add:

- `LayaBackend`: lazy import `laya`, load a configured checkpoint once, call `predict`, normalize `answers` and probabilities, and run no prose generation.
- `OpenJevBackend`: call the configured OpenJev-compatible JSON endpoint with a bounded `httpx.AsyncClient` timeout.
- `JevBackend`: call the configured remote endpoint only when a key is configured; classify HTTP 401/403 as `BackendAuthError`, 408/504/timeouts as `BackendTimeoutError`, and 5xx/network errors as `BackendUnavailableError`.
- `normalize_backend_result`: reject missing answers or non-numeric probabilities instead of returning a success-shaped fallback.

Use injected transports/clients in tests. Do not log request bodies, Authorization headers, or full WhatsApp messages.

- [ ] **Step 4: Add configuration**

Add settings with safe defaults:

```env
DECISION_ROUTER_ENABLED=false
DECISION_BACKENDS=laya,openjev,jev
DECISION_TIMEOUT_SECONDS=2.0
DECISION_CONFIDENCE_THRESHOLD=0.75
LAYA_MODEL=convaiinnovations/laya-multilingual
OPENJEV_URL=
JEV_URL=
JEV_API_KEY=
```

Configuration validation must reject non-positive timeout values and thresholds outside `[0, 1]`.

- [ ] **Step 5: Run backend tests**

Run:

```bash
.venv/bin/pytest -q tests/test_decision_backends.py tests/test_config.py
```

Expected: all tests pass, including secret-redaction assertions.

- [ ] **Step 6: Commit**

```bash
git add app/decision_backends.py app/config.py tests/test_decision_backends.py tests/test_config.py .env.example
git commit -m "feat: add decision backend adapters"
```

### Task 3: Implement ordered fallback and circuit-breaker routing

**Files:**
- Create: `app/decision_router.py`
- Test: `tests/test_decision_router.py`

- [ ] **Step 1: Write failing router tests**

Cover preferred Laya success, OpenJev fallback, Jev fallback, all-backends-failed, low confidence, timeout, and circuit opening:

```python
@pytest.mark.asyncio
async def test_router_uses_openjev_after_laya_failure():
    router = DecisionRouter(
        [FakeBackend("laya", BackendUnavailableError("offline")),
         FakeBackend("openjev", successful_response("openjev"))],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )
    result = await router.decide(valid_request())
    assert result.backend == "openjev"
    assert result.reason_code == "ok"


@pytest.mark.asyncio
async def test_router_marks_low_confidence_for_human_review():
    router = DecisionRouter(
        [FakeBackend("laya", successful_response("laya", confidence=0.41))],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )
    result = await router.decide(valid_request())
    assert result.review_required is True
    assert result.reason_code == "low_confidence"


@pytest.mark.asyncio
async def test_router_returns_explicit_all_backends_failed_state():
    router = DecisionRouter(
        [FakeBackend("laya", BackendTimeoutError("timed out")),
         FakeBackend("openjev", BackendUnavailableError("offline"))],
        timeout_seconds=1,
        confidence_threshold=0.75,
    )
    result = await router.decide(valid_request())
    assert result.backend is None
    assert result.reason_code == "all_backends_failed"
    assert result.review_required is True
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_decision_router.py
```

Expected: import failure for `DecisionRouter`.

- [ ] **Step 3: Implement router behavior**

Implement `DecisionRouter` with:

- ordered backend iteration from configuration;
- `asyncio.wait_for` around each backend call;
- monotonic latency measurement;
- safe reason-code mapping for timeout/auth/unavailable/protocol errors;
- aggregate confidence from response confidence or answer probabilities;
- `review_required=True` when confidence is missing/below threshold or all backends fail;
- per-backend failure counters and an in-memory circuit-open window;
- no silent default answer.

Keep the router usable in tests with injected backends and an injectable clock.

- [ ] **Step 4: Run focused router tests**

```bash
.venv/bin/pytest -q tests/test_decision_router.py
```

Expected: all router tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/decision_router.py tests/test_decision_router.py
git commit -m "feat: add decision backend fallback router"
```

### Task 4: Expose authenticated HTTP decision endpoint

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_decision_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests for authentication, valid decisions, malformed questions, backend failure, and secret-free error responses:

```python
def test_decide_requires_admin_or_session(client):
    response = client.post("/decide", json={"state": "x", "questions": {"q": {"type": "noul", "instructions": "?"}}})
    assert response.status_code in {401, 403}


def test_decide_returns_typed_router_result(authenticated_client, monkeypatch):
    monkeypatch.setattr(app_state, "decision_router", FakeRouter(successful_response("laya")))
    response = authenticated_client.post("/decide", json=valid_request_json())
    assert response.status_code == 200
    assert response.json()["backend"] == "laya"


def test_decide_rejects_unknown_question_type(authenticated_client):
    response = authenticated_client.post("/decide", json={"state": "x", "questions": {"q": {"type": "unknown", "instructions": "?"}}})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify failure**

```bash
.venv/bin/pytest -q tests/test_decision_api.py
```

Expected: route-not-found or missing application router state.

- [ ] **Step 3: Wire the endpoint**

Add `POST /decide` behind the existing session/admin protection. Build the configured router at application startup only when `DECISION_ROUTER_ENABLED=true`; otherwise return a typed `backend_unavailable` response with `review_required=true`, not a 500 or fake answer.

Return `200` for valid decisions, `422` for Pydantic validation failures, and a safe `503` only for infrastructure-level router initialization failure. Keep `GET /healthz` free of credentials and expose only enabled backend names/status in an authenticated status endpoint if needed.

- [ ] **Step 4: Run API tests**

```bash
.venv/bin/pytest -q tests/test_decision_api.py tests/test_api.py
```

Expected: all focused and existing API tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_decision_api.py
git commit -m "feat: expose authenticated decision endpoint"
```

### Task 5: Integrate decisions into LangGraph without changing prose generation

**Files:**
- Modify: `app/graph.py`
- Modify: `app/dashboard_services.py` if chat service constructs graph state
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write failing integration tests**

Add tests that verify decision metadata is passed to the graph, low confidence requests review, and router unavailability preserves the existing LLM response:

```python
def test_graph_uses_decision_for_route_and_language_hint(tmp_path):
    decision_router = FakeRouter(
        successful_decision(
            backend="laya",
            answers={"intent": "research", "language": "roman_urdu", "urgency": "soon"},
            confidence=0.92,
        )
    )
    graph = build_graph(memory, tools, llm=RecordingLLM("Roman Urdu jawab"), decision_router=decision_router)
    result = graph.invoke(local_message("is topic par research karo"))
    assert result["decision"]["backend"] == "laya"
    assert result["route"] == "researcher"


def test_graph_keeps_existing_response_when_decision_router_unavailable(tmp_path):
    graph = build_graph(memory, tools, llm=RecordingLLM("Theek hai"), decision_router=UnavailableRouter())
    result = graph.invoke(local_message("hello"))
    assert result["response"].text == "Theek hai"
    assert result["decision"]["reason_code"] == "backend_unavailable"
```

- [ ] **Step 2: Run tests and verify failure**

```bash
.venv/bin/pytest -q tests/test_graph.py
```

Expected: `build_graph` does not yet accept a decision router or result metadata.

- [ ] **Step 3: Add the bounded graph decision step**

Add an optional decision-router dependency to graph construction. Before the existing supervisor route, request only typed fields required for:

```python
{
    "intent": {"type": "choice", "instructions": "Choose the workflow", "criteria": {
        "personal_assistant": "tasks, reminders, profile",
        "researcher": "research, sources, comparison",
        "developer": "code, errors, debugging",
    }},
    "urgency": {"type": "score", "instructions": "How urgent is this?", "criteria": ["normal", "soon", "blocking"]},
    "escalation": {"type": "noul", "instructions": "Does this require human review?"},
    "language": {"type": "choice", "instructions": "Preferred response language", "criteria": {"roman_urdu": "Roman Urdu", "english": "English"}},
}
```

Use decision intent only when confidence is above threshold; otherwise retain the existing deterministic route logic. Pass safe decision metadata into the state and prompt, never raw credentials or full backend exceptions. Keep the existing prompt rule that the LLM generates natural Roman Urdu and does not translate technical terms unnecessarily.

- [ ] **Step 4: Run graph and policy tests**

```bash
.venv/bin/pytest -q tests/test_graph.py tests/test_policy.py
```

Expected: new integration tests and all existing language-policy tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/graph.py app/dashboard_services.py tests/test_graph.py
git commit -m "feat: integrate typed decisions into LangGraph routing"
```

### Task 6: Add MCP and generic coding-agent adapters

**Files:**
- Create: `app/mcp_decision_server.py`
- Create: `docs/decision-router-agents.md`
- Test: `tests/test_mcp_decision_server.py`

- [ ] **Step 1: Write failing MCP contract tests**

Test the four public operations against a fake router:

```python
def test_mcp_decide_returns_contract_without_model_details():
    result = call_tool("decide", {"state": {"body": "fix login"}, "questions": valid_questions()})
    assert result["backend"] == "laya"
    assert "api_key" not in json.dumps(result)


def test_mcp_review_required_is_true_for_low_confidence():
    result = call_tool("review_required", {"decision": low_confidence_decision()})
    assert result["review_required"] is True
```

- [ ] **Step 2: Run tests and verify failure**

```bash
.venv/bin/pytest -q tests/test_mcp_decision_server.py
```

Expected: import failure for the MCP server module.

- [ ] **Step 3: Implement MCP tools**

Expose `decide`, `route`, `risk_check`, and `review_required` as thin adapters over `DecisionRouter`. They must reuse the exact Pydantic contract and never expose provider secrets or private raw message logs. Require the same auth mechanism used by the deployment environment when the server is reachable over a network.

- [ ] **Step 4: Document agent usage**

Document:

```bash
curl -X POST "$DECISION_URL/decide" \
  -H "Authorization: Bearer $DECISION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"state":{"body":"fix login"},"questions":{"risk":{"type":"noul","instructions":"Is this high risk?"}}}'
```

Include a Python client, MCP configuration shape, Copilot CLI usage pattern, Antigravity local MCP/HTTP bridge guidance, and a generic coding-agent JSON example. State clearly that these agents receive typed decisions; they do not receive model credentials and must respect `review_required`.

- [ ] **Step 5: Run MCP tests**

```bash
.venv/bin/pytest -q tests/test_mcp_decision_server.py
```

Expected: all MCP adapter tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/mcp_decision_server.py tests/test_mcp_decision_server.py docs/decision-router-agents.md
git commit -m "feat: expose decision router to coding agents"
```

### Task 7: Add isolated Laya/OpenJev/Jev smoke scripts

**Files:**
- Create: `scripts/test_laya.py`
- Create: `scripts/test_openjev.py`
- Create: `scripts/benchmark_decisions.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Add optional dependency groups**

Add optional groups without forcing model packages into the production image:

```toml
[project.optional-dependencies]
decision-local = ["laya>=0.1"]
decision-mcp = ["mcp>=1.0"]
```

If OpenJev requires a separate repository or package that conflicts with the app, keep its install command documented in `scripts/test_openjev.py` output and use a separate virtual environment rather than adding an unverified dependency to the application.

- [ ] **Step 2: Implement Laya smoke test**

The script must:

- import `laya`;
- load `convaiinnovations/laya-multilingual`;
- set CPU thread caps from CLI arguments, defaulting to 2;
- run typed department, urgency, and Roman Urdu/Urdu-script fixtures;
- print `status=local`, model name, input length, result, elapsed milliseconds, and process memory when available;
- exit non-zero on import/load/prediction failure.

Run:

```bash
.venv/bin/pip install -e '.[decision-local]'
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python scripts/test_laya.py
```

- [ ] **Step 3: Implement OpenJev smoke test**

Support `OPENJEV_URL` and an explicit `--mock` option. A live run must fail clearly when the URL is absent; a mock run must print `status=mock`, never claim live success, and exercise the same typed request schema.

Run:

```bash
.venv/bin/python scripts/test_openjev.py --mock
OPENJEV_URL=http://127.0.0.1:PORT .venv/bin/python scripts/test_openjev.py
```

- [ ] **Step 4: Implement benchmark script**

Benchmark each available backend on identical fixtures, report median and p95 latency, model/backend, mode (`local`, `mock`, or `live`), and failures. Do not compare unavailable Jev/OpenJev as zero latency or successful throughput.

Run:

```bash
.venv/bin/python scripts/benchmark_decisions.py --iterations 10
```

- [ ] **Step 5: Document installation and limitations**

Update README and deployment docs with:

- Laya installation and CPU settings;
- OpenJev separate-environment setup;
- Jev remote-only status and required credentials;
- sidecar startup and health checks;
- MCP/HTTP coding-agent configuration;
- explicit warning that decision models classify/route and do not replace the chat LLM.

- [ ] **Step 6: Commit**

```bash
git add scripts/test_laya.py scripts/test_openjev.py scripts/benchmark_decisions.py pyproject.toml README.md docs/DEPLOYMENT.md
git commit -m "docs: add decision model installation and benchmarks"
```

### Task 8: Run full validation and write the report

**Files:**
- Create: `docs/superpowers/reports/2026-09-24-system-one-decision-router-validation.md`

- [ ] **Step 1: Run static checks and unit tests**

```bash
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q
```

Expected: Ruff exits 0 and the complete test suite passes.

- [ ] **Step 2: Run local and mock smoke tests**

```bash
.venv/bin/python scripts/test_openjev.py --mock
.venv/bin/python scripts/benchmark_decisions.py --iterations 10 --mock
```

Run the Laya test only if its optional package installation succeeds; otherwise record the exact install/import blocker and do not mark it as passed.

- [ ] **Step 3: Run Jev live test only with explicit credentials**

```bash
if [ -n "${JEV_API_KEY:-}" ] && [ -n "${JEV_URL:-}" ]; then
  .venv/bin/python scripts/benchmark_decisions.py --backend jev --iterations 10
else
  echo "Jev live test skipped: JEV_URL/JEV_API_KEY not configured"
fi
```

- [ ] **Step 4: Write the validation report**

Record commands, environment, package versions, backend mode, latency measurements, memory observations, failures, and exact status for Laya, OpenJev, and Jev. Include a compatibility table:

| Backend | Installation | Mode tested | Result | Notes |
|---|---|---|---|---|
| Laya | local optional environment | local/mock/live | pass/fail | model/checkpoint and CPU data |
| OpenJev | separate environment or endpoint | local/mock/live | pass/fail | URL/package and blocker |
| Jev | remote adapter | contract/mock/live | pass/fail/skipped | never claim local weights |

- [ ] **Step 5: Run final regression**

```bash
.venv/bin/pytest -q
git diff --check
git --no-pager status --short
```

Expected: tests pass, diff check is clean, and only intentional files remain.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/reports/2026-09-24-system-one-decision-router-validation.md
git commit -m "test: record decision router validation results"
```

## Final acceptance checklist

- [ ] Typed decision contract validates inputs and outputs.
- [ ] Laya, OpenJev, and Jev adapters distinguish local, mock, live, unavailable, timeout, and auth states.
- [ ] Fallback router never fabricates a decision and marks uncertain/high-risk cases for review.
- [ ] `/decide` is authenticated and documented.
- [ ] LangGraph uses decisions only for bounded routing hints; Ollama still generates conversational Roman Urdu.
- [ ] MCP and HTTP examples work for Copilot CLI, Antigravity, and generic coding agents without exposing secrets.
- [ ] CPU benchmark output is measured and labeled.
- [ ] Full tests and lint pass.
