# Agent Control Center Full Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the deployed dashboard into an operation-first Agent Control Center with complete agent/provider CRUD, persistent chat and streaming, realtime operations, audit/settings controls, and verified deployment behavior.

**Architecture:** Keep the existing FastAPI application, Next.js dashboard, and encrypted SQLite persistence on the Railway volume. Add focused store/service boundaries behind authenticated routes, use optimistic revisions for configuration, resolve providers by priority with explicit fallback, and treat persisted messages/events as authoritative when SSE disconnects.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite, Fernet-based `EncryptedCodec`, httpx, pytest, Next.js 15, React 19, TypeScript, ESLint, Railway.

---

## File map

- Modify `app/dashboard_models.py`: add typed conversation, message, settings, provider-test, and paginated response contracts.
- Modify `app/dashboard_store.py`: add encrypted conversation/message/settings persistence, revision-safe updates, and bounded pagination.
- Modify `app/providers.py`: add streaming generation, connection tests, normalized errors, and provider-priority resolution.
- Create `app/dashboard_services.py`: keep agent/provider/chat orchestration out of the route handlers.
- Modify `app/api.py`: expose authenticated CRUD, provider test, chat history/streaming, operations, settings, and audit pagination routes.
- Modify `app/events.py`: add stable SSE cursors and chat chunk events while preserving redaction.
- Modify `tests/test_dashboard_store.py`: persistence and pagination tests.
- Modify `tests/test_dashboard_api.py`: authenticated API workflows, conflicts, deletes, chat, audit, and settings tests.
- Modify `tests/test_providers.py`: bearer headers, connection tests, streaming, and fallback tests.
- Create `tests/test_dashboard_services.py`: service-level agent/provider/chat behavior.
- Modify `dashboard/app/page.tsx`: operation-first shell, editor forms, conversation UI, and explicit async states.
- Modify `dashboard/app/globals.css`: responsive forms, messages, status badges, modal confirmation, and stream states.
- Modify `dashboard/package.json` only if a focused frontend test dependency is already needed; do not add a new test framework for this plan.
- Modify `docs/DEPLOYMENT.md` and `.env.example`: document dashboard persistence, provider setup, smoke checks, and required Railway values.

### Task 1: Add durable dashboard domain contracts and SQLite storage

**Files:**
- Modify: `app/dashboard_models.py`
- Modify: `app/dashboard_store.py`
- Test: `tests/test_dashboard_store.py`

- [ ] **Step 1: Write failing persistence tests**

Add tests for a conversation and messages surviving a new `DashboardStore` instance, for sequence-based message pagination, and for settings round-tripping without exposing secrets:

```python
def test_conversation_and_messages_survive_store_restart(tmp_path):
    first = DashboardStore(tmp_path / "memory.db", "secret")
    conversation = first.create_conversation("c1", "owner", "agent-1")
    first.append_message("m1", "c1", "user", "salam")
    first.append_message("m2", "c1", "assistant", "Walaikum salam")

    second = DashboardStore(tmp_path / "memory.db", "secret")
    assert second.get_conversation("c1") == conversation
    assert [message.id for message in second.list_messages("c1")] == ["m1", "m2"]


def test_message_pagination_returns_next_cursor(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    store.create_conversation("c1", "owner", None)
    for index in range(3):
        store.append_message(f"m{index}", "c1", "user", str(index))

    page, cursor = store.list_messages("c1", after=0, limit=2)
    assert [message.id for message in page] == ["m0", "m1"]
    assert cursor == 2


def test_settings_are_encrypted_and_round_trip(tmp_path):
    store = DashboardStore(tmp_path / "memory.db", "secret")
    store.set_setting("default_agent_id", "agent-1")
    assert store.get_setting("default_agent_id") == "agent-1"
    assert b"agent-1" not in (tmp_path / "memory.db").read_bytes()
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_dashboard_store.py -q`

Expected: FAIL because the conversation/message/settings contracts and store methods do not exist.

- [ ] **Step 3: Add the domain contracts**

Add models with explicit fields and validation:

```python
class ConversationRecord(BaseModel):
    id: str
    actor: str
    agent_id: str | None = None
    title: str = "New conversation"
    created_at: datetime
    updated_at: datetime


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    provider_id: str | None = None
    created_at: datetime
    complete: bool = True


class SettingsRecord(BaseModel):
    key: str
    value: str
```

- [ ] **Step 4: Add encrypted tables and store methods**

Extend `DashboardStore.__init__` with `dashboard_conversations`, `dashboard_messages`, and `dashboard_settings` tables. Implement `create_conversation`, `get_conversation`, `list_conversations`, `append_message`, `list_messages`, `set_setting`, and `get_setting`. Store JSON through `self.codec.dumps`, order by SQLite sequence, and return a cursor equal to the last returned sequence. Never store plaintext values in the new tables.

- [ ] **Step 5: Run the focused tests and the existing store suite**

Run: `pytest tests/test_dashboard_store.py -q`

Expected: all store tests pass, including existing provider/agent encryption and revision tests.

- [ ] **Step 6: Commit the storage slice**

```bash
git add app/dashboard_models.py app/dashboard_store.py tests/test_dashboard_store.py
git commit -m "feat: persist dashboard conversations and settings"
```

### Task 2: Build provider and agent services with fallback and safe tests

**Files:**
- Modify: `app/providers.py`
- Create: `app/dashboard_services.py`
- Test: `tests/test_providers.py`
- Test: `tests/test_dashboard_services.py`

- [ ] **Step 1: Write failing provider and service tests**

Use `httpx.MockTransport` or monkeypatch `httpx.AsyncClient` to assert the real secret is sent only in the request header, and add fallback tests:

```python
@pytest.mark.asyncio
async def test_ollama_sends_configured_secret_as_bearer(monkeypatch, store):
    captured = {}

    async def send(request):
        captured["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={"message": {"content": "ok"}})

    monkeypatch.setattr(httpx.AsyncClient, "__aenter__", lambda self: _Client(send))
    provider = provider_from_config(store, ollama_config)
    assert await provider.generate([{"role": "user", "content": "hi"}]) == "ok"
    assert captured["authorization"] == "Bearer real-secret"


@pytest.mark.asyncio
async def test_chat_service_uses_next_provider_after_failure(service):
    result = await service.generate("hello", agent_id="agent-1")
    assert result.text == "fallback reply"
    assert result.provider_id == "backup"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_providers.py tests/test_dashboard_services.py -q`

Expected: FAIL because streaming/test methods, service classes, and priority resolution are missing.

- [ ] **Step 3: Extend the provider protocol and adapters**

Define `ProviderResult`, `ProviderError(provider_id, retryable, safe_detail)`, `generate_stream`, and `test_connection`. Implement Ollama NDJSON parsing and OpenAI-compatible SSE parsing with bounded timeouts. Keep error text status-based and never include request headers or response bodies that may contain credentials.

- [ ] **Step 4: Add `dashboard_services.py` orchestration**

Implement:

```python
class AgentService:
    def save(self, agent: AgentConfig, expected_revision: int | None) -> AgentConfig: ...
    def delete(self, agent_id: str, expected_revision: int | None) -> None: ...


class ProviderService:
    def save(self, provider: ProviderConfig, secret: str | None, expected_revision: int | None) -> ProviderConfig: ...
    async def test(self, provider_id: str) -> ProviderTestResult: ...
    def ordered(self, agent: AgentConfig) -> list[ProviderConfig]: ...


class ChatService:
    async def generate(self, actor: str, text: str, conversation_id: str | None, agent_id: str | None) -> ChatResult: ...
    async def stream(self, actor: str, text: str, conversation_id: str | None, agent_id: str | None): ...
```

`ProviderService.ordered` must use the agent's `provider_ids` order first, then enabled providers by ascending `priority`; duplicate IDs appear once. `ChatService` persists the user message before trying providers, records a complete assistant message only after success, and returns a safe error after all providers fail.

- [ ] **Step 5: Run provider and service tests**

Run: `pytest tests/test_providers.py tests/test_dashboard_services.py -q`

Expected: PASS with bearer-header, streaming, connection-test, ordering, and fallback coverage.

- [ ] **Step 6: Commit the service slice**

```bash
git add app/providers.py app/dashboard_services.py tests/test_providers.py tests/test_dashboard_services.py
git commit -m "feat: add dashboard provider and chat services"
```

### Task 3: Expose complete authenticated dashboard APIs

**Files:**
- Modify: `app/api.py`
- Modify: `app/events.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing API workflow tests**

Cover create/update/delete for agents and providers, stale revision `409`, provider test masking, conversation creation, history retrieval, chat errors, event cursors, audit pagination, and settings:

```python
def test_agent_update_requires_current_revision(client):
    created = client.post("/dashboard/agents", json=agent_payload).json()
    stale = {**agent_payload, "revision": created["revision"] - 1, "name": "changed"}
    response = client.put(f"/dashboard/agents/{created['id']}", json=stale)
    assert response.status_code == 409
    assert "revision" in response.json()["detail"]


def test_chat_persists_history_and_returns_conversation_id(client):
    response = client.post("/dashboard/chat", json={"text": "salam"})
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    history = client.get(f"/dashboard/conversations/{conversation_id}/messages")
    assert [item["role"] for item in history.json()["messages"]] == ["user", "assistant"]


def test_unauthenticated_stream_is_rejected(client):
    client.post("/auth/logout")
    assert client.get("/dashboard/events/stream").status_code == 401
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `pytest tests/test_dashboard_api.py -q`

Expected: FAIL for missing PUT, provider test, conversation/history, cursor, and settings routes.

- [ ] **Step 3: Add authenticated route helpers**

Create route-local request models or Pydantic body validation for `expected_revision`, `secret`, `agent_id`, `conversation_id`, `text`, `cursor`, and `limit`. Convert store `ValueError` revision conflicts to `HTTPException(409)` and store `KeyError` to `404`. Add `PUT` to CORS methods.

- [ ] **Step 4: Wire CRUD and provider test routes**

Add:

```text
PUT    /dashboard/agents/{agent_id}
DELETE /dashboard/agents/{agent_id}
PUT    /dashboard/providers/{provider_id}
DELETE /dashboard/providers/{provider_id}
POST   /dashboard/providers/{provider_id}/test
```

Every mutation appends an audit record and a redacted `config_changed` event. Provider test responses contain status, provider ID, latency, and safe error text only.

- [ ] **Step 5: Wire conversations, chat, events, audit, and settings**

Add:

```text
GET  /dashboard/conversations
POST /dashboard/conversations
GET  /dashboard/conversations/{conversation_id}/messages
POST /dashboard/chat
GET  /dashboard/chat/stream
GET  /dashboard/audit?cursor=0&limit=100
GET  /dashboard/settings
PUT  /dashboard/settings
```

The streaming endpoint emits `event: chunk`, `event: complete`, and `event: error` records with a stable `id`. `EventRecorder` must redact keys matching `secret`, `token`, `authorization`, `api_key`, and `password` before both SQLite persistence and SSE.

- [ ] **Step 6: Run the full backend suite**

Run: `pytest -q && ruff check . && python -m compileall app`

Expected: all tests pass, Ruff reports no violations, and compilation exits zero.

- [ ] **Step 7: Commit the API slice**

```bash
git add app/api.py app/events.py tests/test_dashboard_api.py
git commit -m "feat: expose complete dashboard control APIs"
```

### Task 4: Replace the minimal dashboard with functional operation-first screens

**Files:**
- Modify: `dashboard/app/page.tsx`
- Modify: `dashboard/app/globals.css`

- [ ] **Step 1: Add typed client contracts and request state**

Define TypeScript interfaces for `Agent`, `Provider`, `Conversation`, `Message`, `RuntimeEvent`, and paginated API responses. Replace `Record<string, unknown>` with typed state. Implement one `request<T>` helper that parses JSON safely, preserves `409` details, and throws an `ApiError` with `status`.

- [ ] **Step 2: Add agent editor behavior**

Render a form with name, system prompt, response language, memory profile, tools, provider priority, and enabled state. On save send `POST` for new agents and `PUT` with the current revision for existing agents. On `409`, keep the form values and display “configuration changed; reload latest”. Delete only after `window.confirm` and refresh overview/list state.

- [ ] **Step 3: Add provider manager behavior**

Render type, name, base URL, model, secret input, enabled state, priority, save, connection-test, and delete controls. Display only `has_secret`/last-four metadata. Disable test/save while pending and show provider-test latency/result. Do not place the secret in component logs, URL parameters, or rendered JSON.

- [ ] **Step 4: Add persistent chat UI**

Load conversations, create a conversation, load messages, submit a user message, append an optimistic pending message, consume `/dashboard/chat/stream`, mark the assistant message complete on `complete`, and retain the pending/error state on `error`. Offer retry using the same conversation and show the selected agent/provider/fallback metadata.

- [ ] **Step 5: Add operations, audit, and settings screens**

Overview must show `/dashboard/overview` status and worker error. Live Activity must use `EventSource`, reconnect with backoff, and preserve the last cursor. Audit must request pages using the returned cursor. Settings must expose only non-secret values and require confirmation for runtime/destructive actions.

- [ ] **Step 6: Add responsive styles and accessibility**

Add styles for forms, message roles, status badges, validation errors, confirmation dialog, disconnected stream state, and mobile navigation. Use labels associated with every input, keyboard-focusable buttons, semantic headings, and an `aria-live="polite"` region for streaming status.

- [ ] **Step 7: Run frontend checks**

Run: `cd dashboard && npm ci && npm run typecheck && npm run lint && npm run build`

Expected: TypeScript, ESLint, and the production build all pass.

- [ ] **Step 8: Commit the frontend slice**

```bash
git add dashboard/app/page.tsx dashboard/app/globals.css
git commit -m "feat: complete dashboard control center UI"
```

### Task 5: Complete lifecycle events, docs, and deployment configuration

**Files:**
- Modify: `app/api.py`
- Modify: `app/config.py`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `.env.example`
- Modify: `.github/workflows/deploy-railway.yml`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write lifecycle event tests**

Assert `message_received`, `agent_selected`, `provider_attempt`, `response_ready`, `response_failed`, and `message_delivered` are emitted for a successful dashboard/WhatsApp processing path, and that failure events contain no secret-like keys.

- [ ] **Step 2: Emit events at receive/process/send boundaries**

Add a small internal event helper in `create_app` that records the correlation ID and safe metadata. Call it in `process_messages`, dashboard chat, provider fallback attempts, and outbound WhatsApp delivery. Preserve existing duplicate-message behavior and never emit message contents or credentials.

- [ ] **Step 3: Add runtime/settings contracts**

Expose read-only runtime status and validated non-secret settings. Keep worker restart/disable actions explicit and authenticated; do not create a second polling task or alter the one-replica deployment rule.

- [ ] **Step 4: Document deployment and smoke checks**

Document `MEMORY_KEY`, `DASHBOARD_ORIGIN`, owner credentials/hash, Railway volume `/app/data`, port `8080`, one backend replica, separate dashboard service, and this smoke sequence:

```bash
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/healthz
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/readyz
curl -I https://agent-dashboard-production-10fc.up.railway.app
```

Document that GitHub Actions requires separate Railway token/project/service secrets for backend and dashboard deployments.

- [ ] **Step 5: Run backend and frontend checks**

Run: `pytest -q && ruff check . && cd dashboard && npm run typecheck && npm run lint && npm run build`

Expected: all checks pass.

- [ ] **Step 6: Commit operational completion**

```bash
git add app/api.py app/config.py docs/DEPLOYMENT.md .env.example .github/workflows/deploy-railway.yml tests/test_dashboard_api.py
git commit -m "feat: complete dashboard lifecycle operations"
```

### Task 6: Verify the deployed services and prepare the branch

**Files:**
- No source changes unless a smoke test identifies a concrete defect.

- [ ] **Step 1: Build and deploy the backend and dashboard services**

Deploy the backend and dashboard from the `fix/dashboard-loading` worktree using the existing Railway project/service configuration. Confirm both deployment IDs reach `SUCCESS`; do not increase backend replicas.

- [ ] **Step 2: Run deployed health and readiness checks**

Run:

```bash
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/healthz
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/readyz
curl -fsS https://agent-dashboard-production-10fc.up.railway.app
```

Expected: health returns `{"status":"ok"}`, readiness reports the WhatsApp worker as `ok` or `disabled` according to configuration, and the dashboard returns HTML plus HTTP 200 static assets.

- [ ] **Step 3: Execute the authenticated smoke workflow**

Using a temporary cookie jar and the configured owner credentials, exercise login, overview, agent create/update/delete, provider create/test/delete, conversation create, chat, history, activity, and audit. Verify response bodies never contain the provider secret.

- [ ] **Step 4: Inspect the final worktree**

Run:

```bash
git status --short
git log -5 --oneline --decorate
```

Expected: only intentional committed changes are present, and the branch contains the design, plan, implementation slices, and verification commits.

- [ ] **Step 5: Push and open/update the dashboard pull request**

```bash
git push origin fix/dashboard-loading
gh pr list --head fix/dashboard-loading --state open
```

Update the existing dashboard PR if present; otherwise open one with the backend/frontend test results and deployed smoke URLs. Do not merge until CI is green and the single-worker constraint is confirmed.
