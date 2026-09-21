# Personal WhatsApp AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Docker-ready LangChain/LangGraph personal agent that uses Ollama Cloud, encrypted local memory, Roman Urdu responses, permission-gated tools, and an isolated adapter for the official WhatsApp personal-agent API.

**Architecture:** A FastAPI gateway accepts local and WhatsApp-shaped messages, then invokes a LangGraph supervisor. The graph uses focused role nodes and LangChain tools, while an encrypted SQLite-backed memory service stores only approved profile and task data. WhatsApp payload details remain behind an adapter interface so the core agent can be tested without undocumented or unofficial WhatsApp automation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, LangChain, LangGraph, `langchain-ollama`, `cryptography` Fernet, SQLite, pytest, httpx, Docker Compose.

---

## File map

Create the following focused modules:

- `pyproject.toml`: runtime and test dependencies plus tool configuration.
- `.env.example`: non-secret configuration contract.
- `.gitignore`: secrets, local data, caches, and generated files.
- `app/config.py`: validated settings.
- `app/contracts.py`: message, response, memory, tool, and adapter contracts.
- `app/security.py`: secret loading, encryption, redaction, and permission checks.
- `app/memory.py`: encrypted SQLite profile, preferences, summaries, and tasks.
- `app/llm.py`: Ollama Cloud LangChain model factory and bounded retry policy.
- `app/policy.py`: Roman Urdu output policy and sensitive-data/confirmation policy.
- `app/tools.py`: typed LangChain tools and tool registry.
- `app/graph.py`: LangGraph state, supervisor routing, role nodes, and execution.
- `app/whatsapp.py`: official-adapter interface plus mock adapter only.
- `app/api.py`: health, local message, webhook-shaped receive, and response endpoints.
- `app/cli.py`: local terminal entry point.
- `app/main.py`: ASGI entry point.
- `tests/`: unit, integration, security, and API tests.
- `Dockerfile`, `docker-compose.yml`: local runtime and encrypted data volume.
- `README.md`: setup, secret handling, local use, and official WhatsApp adapter boundary.

The first plan is intentionally one implementation plan because the gateway,
graph, memory, and adapter are independently testable parts of one local MVP;
the WhatsApp provider contract remains an adapter task rather than a second
unbounded product.

### Task 1: Create the Python project skeleton and configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing configuration test**

```python
from app.config import Settings


def test_settings_use_safe_local_defaults(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    settings = Settings(
        memory_path="data/memory.db",
        memory_key="test-key",
        whatsapp_enabled=False,
    )
    assert settings.ollama_model == "nemotron-3-nano:30b-cloud"
    assert settings.response_language == "roman_urdu"
    assert settings.whatsapp_enabled is False
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_config.py -q`

Expected: FAIL because the package and `Settings` class do not exist.

- [ ] **Step 3: Add the project metadata and settings implementation**

`pyproject.toml` must declare Python 3.12, FastAPI, Uvicorn, Pydantic
settings, LangChain, LangGraph, `langchain-ollama`, cryptography, httpx,
pytest, pytest-asyncio, and ruff. Define `agent-api = "app.cli:main"` and
pytest discovery under `tests`.

Implement `Settings` with these fields and defaults:

```python
class Settings(BaseSettings):
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "nemotron-3-nano:30b-cloud"
    ollama_api_key: SecretStr | None = None
    memory_path: Path = Path("data/memory.db")
    memory_key: SecretStr
    whatsapp_enabled: bool = False
    whatsapp_api_key: SecretStr | None = None
    response_language: Literal["roman_urdu"] = "roman_urdu"
    max_tool_seconds: float = 15.0
    max_response_chars: int = 3000
```

Reject a blank `memory_key`; load `.env` but never log secret values.

- [ ] **Step 4: Run the configuration test**

Run: `pytest tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the project skeleton**

Run:

```bash
git add pyproject.toml .env.example .gitignore app tests
git commit -m "chore: scaffold personal agent runtime"
```

Expected: this workspace currently has no Git repository, so if commit fails
with `not a git repository`, retain the files and report that commit is blocked
without initializing or altering repository history.

### Task 2: Define contracts, encryption, and permission policy

**Files:**
- Create: `app/contracts.py`
- Create: `app/security.py`
- Create: `tests/test_security.py`
- Create: `tests/test_contracts.py`

- [ ] **Step 1: Write failing contract and security tests**

```python
from app.security import EncryptedCodec, redact_contact_fields


def test_encrypted_codec_round_trips_and_hides_plaintext():
    codec = EncryptedCodec("unit-test-secret")
    token = codec.encrypt(b'{"phone":"03105287479"}')
    assert token != b'{"phone":"03105287479"}'
    assert codec.decrypt(token) == b'{"phone":"03105287479"}'


def test_contact_fields_are_redacted_by_default():
    result = redact_contact_fields({"name": "Danyal", "email": "x@example.com"})
    assert result == {"name": "Danyal", "email": "[protected]"}
```

```python
from app.contracts import IncomingMessage, OutgoingMessage


def test_message_contract_requires_id_and_text():
    message = IncomingMessage(message_id="m-1", sender_id="self", text="hello")
    assert message.text == "hello"
    assert OutgoingMessage(message_id="m-1", text="jawab").text == "jawab"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_security.py tests/test_contracts.py -q`

Expected: FAIL because contracts and security helpers do not exist.

- [ ] **Step 3: Implement contracts and security primitives**

Define Pydantic models:

```python
class IncomingMessage(BaseModel):
    message_id: str
    sender_id: str
    text: str
    timestamp: datetime = Field(default_factory=datetime.now, tzinfo=UTC)
    source: Literal["local", "whatsapp"] = "local"

class OutgoingMessage(BaseModel):
    message_id: str
    text: str
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
```

Implement Fernet-based `EncryptedCodec`, constant-time permission checks,
contact redaction, and `require_confirmation(action, confirmed)` that returns
`False` unless the caller explicitly confirmed the exact action.

- [ ] **Step 4: Run security and contract tests**

Run: `pytest tests/test_security.py tests/test_contracts.py -q`

Expected: PASS, including a test that a wrong encryption key raises a clear
decryption error rather than returning fallback plaintext.

### Task 3: Build encrypted SQLite memory

**Files:**
- Create: `app/memory.py`
- Create: `tests/test_memory.py`

- [ ] **Step 1: Write failing memory tests**

```python
def test_profile_is_encrypted_and_contact_fields_are_protected(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", "memory-secret")
    store.save_profile({"name": "Danyal", "email": "danyal@example.com"})
    assert store.get_profile(include_contacts=False) == {
        "name": "Danyal",
        "email": "[protected]",
    }
    assert b"danyal@example.com" not in (tmp_path / "memory.db").read_bytes()


def test_memory_can_be_forgotten_and_exported(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", "memory-secret")
    store.save_preference("language", "roman_urdu")
    assert store.export_json()["preferences"]["language"] == "roman_urdu"
    store.forget("preferences")
    assert store.export_json()["preferences"] == {}
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `pytest tests/test_memory.py -q`

Expected: FAIL because `MemoryStore` does not exist.

- [ ] **Step 3: Implement the memory store**

Create SQLite tables `kv_memory`, `preferences`, `summaries`, `tasks`, and
`processed_events`. Serialize each value as JSON, encrypt the serialized bytes
with `EncryptedCodec`, and store only ciphertext in the database. Implement:

```python
class MemoryStore:
    def save_profile(self, profile: dict[str, object]) -> None: ...
    def get_profile(self, include_contacts: bool = False) -> dict[str, object]: ...
    def save_preference(self, key: str, value: object) -> None: ...
    def save_summary(self, thread_id: str, summary: str) -> None: ...
    def create_task(self, title: str, due_at: str | None = None) -> str: ...
    def list_tasks(self, status: str = "open") -> list[dict[str, object]]: ...
    def forget(self, category: Literal["profile", "preferences", "summaries", "tasks"]) -> None: ...
    def export_json(self) -> dict[str, object]: ...
    def mark_event_if_new(self, event_id: str) -> bool: ...
```

Make all writes transactional and ensure `mark_event_if_new` is atomic so
duplicate webhook deliveries cannot execute twice.

- [ ] **Step 4: Run memory tests**

Run: `pytest tests/test_memory.py -q`

Expected: PASS, including the ciphertext assertion and forget/export behavior.

### Task 4: Add Ollama Cloud model and Roman Urdu response policy

**Files:**
- Create: `app/llm.py`
- Create: `app/policy.py`
- Create: `tests/test_policy.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write failing policy/model tests**

```python
def test_policy_requires_roman_urdu_and_preserves_citations():
    text = apply_response_policy("The answer is ready.\nSource: https://example.com")
    assert "Roman Urdu" in text
    assert "https://example.com" in text


def test_model_factory_does_not_create_a_model_without_an_api_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_API_KEY"):
        create_ollama_chat_model(Settings(memory_key="test-key"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_policy.py tests/test_llm.py -q`

Expected: FAIL because the policy and model factory do not exist.

- [ ] **Step 3: Implement the model adapter**

`create_ollama_chat_model(settings)` must construct
`ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url,
client_kwargs={"headers": {"Authorization": f"Bearer {key}"}})` or the
supported `langchain-ollama` authentication option. Do not print the key.
Wrap invocation in a bounded retry helper for transient 429/5xx failures and
raise `ProviderUnavailableError` after the retry limit.

- [ ] **Step 4: Implement response policy**

`apply_response_policy(text, citations=(), max_chars=3000)` must instruct the
LLM/system prompt to answer in Roman Urdu, preserve URLs, truncate only at a
sentence boundary where possible, and never claim an unexecuted action. Add
`requires_confirmation_for(action)` for profile disclosure, GitHub writes,
outbound messages, and destructive operations.

- [ ] **Step 5: Run policy/model tests**

Run: `pytest tests/test_policy.py tests/test_llm.py -q`

Expected: PASS; mocked model tests must verify provider errors are explicit.

### Task 5: Implement permission-gated LangChain tools

**Files:**
- Create: `app/tools.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing tool tests**

```python
def test_profile_tool_masks_contact_fields_by_default(memory):
    tool = build_tool_registry(memory)["profile_lookup"]
    result = tool.invoke({"field": "email", "confirmed": False})
    assert result.ok is True
    assert result.content == "[protected]"


def test_github_write_is_rejected_without_confirmation(registry):
    result = registry["github_write"].invoke(
        {"operation": "comment", "payload": "hello", "confirmed": False}
    )
    assert result.ok is False
    assert result.error_code == "confirmation_required"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_tools.py -q`

Expected: FAIL because the registry and tools do not exist.

- [ ] **Step 3: Implement the tool registry**

Use Pydantic argument schemas and `@tool` wrappers for:
`profile_lookup`, `notes_create`, `notes_list`, `task_create`, `task_list`,
`research_search`, `workspace_read`, `github_read`, `github_write`, and
`calculate`. Every wrapper returns `ToolResult`, enforces a role allowlist,
uses `Settings.max_tool_seconds`, and records an audit event without storing
secrets or raw protected values.

The research implementation must return source URLs and an explicit
`research_unavailable` result when no provider is configured. The developer
tool may read only paths under the configured workspace root and must reject
path traversal, shell metacharacters, and write operations.

- [ ] **Step 4: Run tool tests**

Run: `pytest tests/test_tools.py -q`

Expected: PASS, including path traversal, contact disclosure, and confirmation
tests.

### Task 6: Build the LangGraph supervisor and role nodes

**Files:**
- Create: `app/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing graph tests**

```python
@pytest.mark.parametrize(
    ("text", "route"),
    [
        ("meri tasks dikhao", "personal_assistant"),
        ("is topic par sources ke sath research karo", "researcher"),
        ("is Python error ko debug karo", "developer"),
    ],
)
def test_supervisor_routes_requests(text, route, graph):
    result = graph.invoke(local_message(text))
    assert result["route"] == route


def test_graph_returns_explicit_provider_failure(graph):
    result = graph.invoke(local_message("research karo"))
    assert "unavailable" in result["response"].text.lower()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_graph.py -q`

Expected: FAIL because the graph factory does not exist.

- [ ] **Step 3: Implement graph state and routing**

Create `build_graph(settings, memory, llm, tools)` with nodes:
`load_memory`, `supervisor`, `personal_assistant`, `researcher`, `developer`,
`apply_policy`, and `persist_summary`. The supervisor must route using
deterministic keyword rules in tests and an LLM classifier only as a fallback.
No role may call tools outside its allowlist.

The personal node handles notes/tasks/profile commands; researcher calls only
research and calculator; developer calls workspace/GitHub read tools. All
nodes return structured state and convert known provider/tool failures into
user-visible Roman Urdu messages.

- [ ] **Step 4: Run graph tests**

Run: `pytest tests/test_graph.py -q`

Expected: PASS with mocked LLM and tool registry.

### Task 7: Add local API, CLI, and official WhatsApp adapter boundary

**Files:**
- Create: `app/whatsapp.py`
- Create: `app/api.py`
- Create: `app/cli.py`
- Create: `app/main.py`
- Create: `tests/test_api.py`
- Create: `tests/test_whatsapp.py`

- [ ] **Step 1: Write failing adapter/API tests**

```python
def test_mock_adapter_round_trips_internal_message():
    adapter = MockWhatsAppAdapter()
    incoming = adapter.parse({"id": "w-1", "from": "self", "text": "hello"})
    assert incoming.source == "whatsapp"
    assert adapter.serialize(OutgoingMessage(message_id="w-1", text="jawab")) == {
        "message_id": "w-1",
        "text": "jawab",
    }


def test_duplicate_webhook_is_not_processed_twice(client):
    payload = {"id": "w-1", "from": "self", "text": "meri tasks dikhao"}
    first = client.post("/webhooks/whatsapp", json=payload)
    second = client.post("/webhooks/whatsapp", json=payload)
    assert first.status_code == 200
    assert second.json()["status"] == "duplicate"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_api.py tests/test_whatsapp.py -q`

Expected: FAIL because the adapter and FastAPI routes do not exist.

- [ ] **Step 3: Implement the adapter and API**

Define:

```python
class WhatsAppAdapter(Protocol):
    def parse(self, payload: dict[str, object]) -> IncomingMessage: ...
    async def send(self, message: OutgoingMessage) -> dict[str, object]: ...

class MockWhatsAppAdapter:
    ...

class OfficialWhatsAppAdapter:
    """Contract boundary; no undocumented endpoint or Web automation."""
    ...
```

`OfficialWhatsAppAdapter` must fail closed with
`whatsapp_contract_not_configured` until the actual account-specific official
payload contract is supplied. It may not guess endpoints or pretend delivery.

Add:

- `GET /healthz` and `GET /readyz`
- `POST /messages` for local `IncomingMessage` requests
- `POST /webhooks/whatsapp` for adapter-shaped payloads
- `GET /memory/export` and `POST /memory/forget` with local authentication

Validate payloads, enforce body size limits, assign request IDs, call
`mark_event_if_new`, and return explicit error JSON. Never include secrets in
responses or logs.

- [ ] **Step 4: Implement the CLI**

`agent-api chat` reads one line at a time, invokes the same graph as the API,
prints only the final Roman Urdu response, and exits non-zero on provider or
configuration errors.

- [ ] **Step 5: Run API and adapter tests**

Run: `pytest tests/test_api.py tests/test_whatsapp.py -q`

Expected: PASS, including duplicate-event and fail-closed official-adapter
tests.

### Task 8: Add Docker runtime, integration tests, and documentation

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `tests/test_integration.py`
- Create: `README.md`

- [ ] **Step 1: Write the integration test**

```python
def test_local_message_uses_graph_and_returns_roman_urdu(client):
    response = client.post(
        "/messages",
        json={"message_id": "local-1", "sender_id": "self", "text": "meri profile batao"},
    )
    assert response.status_code == 200
    assert response.json()["text"]
    assert response.json()["message_id"] == "local-1"
```

- [ ] **Step 2: Implement Docker files**

The `Dockerfile` must install the locked project dependencies, run as a
non-root user, create `/app/data`, and start Uvicorn on port 8000. Compose must
mount only `./data:/app/data`, expose `8000`, load `.env`, and include health
checks. No Ollama secret may appear in either file.

- [ ] **Step 3: Add integration wiring**

Create an application factory that constructs settings, memory, model, tools,
graph, and adapter once per process. In tests, inject fake model and mock
adapter so no network access is required. Verify health, local message,
memory-export permission, provider failure, and duplicate WhatsApp event flow.

- [ ] **Step 4: Run the complete test suite**

Run: `pytest -q`

Expected: all tests pass without network access and without requiring
`OLLAMA_API_KEY` when the fake model fixture is used.

- [ ] **Step 5: Run lint and Docker validation**

Run:

```bash
ruff check .
docker compose config
docker build -t personal-agent:local .
```

Expected: ruff has no errors, Compose renders a valid configuration, and the
image builds successfully.

- [ ] **Step 6: Document setup and boundaries**

`README.md` must include exact commands for creating the virtual environment,
generating a Fernet memory key, setting `OLLAMA_API_KEY`, running CLI/API
locally, running tests, backing up encrypted data, and starting Docker.
Document that the official WhatsApp adapter cannot be activated until Meta's
account-specific custom-agent API contract and privacy terms are confirmed.
Explicitly state that personal-agent chats may not have ordinary end-to-end
encryption and that users must review Meta's current terms before enabling it.

## Final verification checklist

- [ ] `pytest -q` passes without external network access.
- [ ] `ruff check .` passes.
- [ ] `docker compose config` and image build pass.
- [ ] Profile ciphertext contains no plaintext contact values.
- [ ] Roman Urdu is applied on every successful response.
- [ ] Contact disclosure, GitHub writes, outbound messages, and destructive
      operations require explicit confirmation.
- [ ] Duplicate webhook IDs are idempotent.
- [ ] Ollama and WhatsApp failures are explicit.
- [ ] No unofficial WhatsApp automation or guessed Meta endpoint is present.
