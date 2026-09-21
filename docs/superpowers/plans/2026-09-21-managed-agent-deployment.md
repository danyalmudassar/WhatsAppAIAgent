# Managed Agent Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LangGraph/Ollama/official WhatsApp agent deployable as one secure, always-on Docker service on Render or Railway.

**Architecture:** Keep FastAPI and exactly one WhatsApp long-poll worker in the same container. Persist encrypted SQLite memory and the WhatsApp offset on a mounted data volume, protect non-health endpoints with an admin token, and expose platform-compatible health/readiness checks. Render and Railway use the same image and single-replica rule.

**Tech Stack:** Python 3.12, FastAPI/Uvicorn lifespan, httpx, Pydantic Settings, SQLite, Docker Compose, Render Blueprint YAML, Railway configuration, pytest, Ruff.

---

## File map

- Modify `app/config.py`: production settings, platform port, admin token, polling/backoff limits.
- Modify `app/memory.py`: encrypted persistent offset storage.
- Modify `app/api.py`: readiness checks, admin authentication, bounded worker lifecycle, generic errors.
- Modify `app/whatsapp.py`: retry-safe polling and offset persistence integration.
- Modify `app/main.py`: application factory entrypoint compatible with platform `$PORT`.
- Modify `tests/test_api.py`: endpoint authentication and readiness tests.
- Modify `tests/test_memory.py`: encrypted offset persistence tests.
- Modify `tests/test_whatsapp.py`: empty poll/retry and offset tests.
- Create `render.yaml`: single Render web service, persistent disk, health path, one replica.
- Create `railway.toml`: Railway build/deploy health configuration.
- Modify `Dockerfile`: production environment, platform port, non-root runtime, healthcheck.
- Modify `docker-compose.yml`: persistent volume, env contract, healthcheck, one service.
- Modify `.env.example`: all production variables with safe placeholders.
- Modify `.gitignore`: deployment secrets and runtime data exclusions.
- Modify `README.md`: Render/Railway setup, secrets, storage, logs, rollback, and smoke tests.

No separate worker service is planned: a second poller would create offset and
duplicate-delivery races, and SQLite cannot safely serve as a shared store
between independent containers.

### Task 1: Add production configuration and readiness contracts

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_readiness.py`

- [ ] **Step 1: Write failing configuration tests**

```python
def test_platform_defaults_use_port_and_admin_token():
    settings = Settings(
        _env_file=None,
        memory_key="memory",
        app_admin_token="admin-secret",
        port=9000,
    )
    assert settings.port == 9000
    assert settings.app_admin_token.get_secret_value() == "admin-secret"
    assert settings.whatsapp_poll_interval == 1.0


def test_blank_admin_token_is_rejected():
    with pytest.raises(ValueError, match="APP_ADMIN_TOKEN"):
        Settings(_env_file=None, memory_key="memory", app_admin_token=" ")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/pytest tests/test_config.py tests/test_readiness.py -q`

Expected: FAIL because `port`, `app_admin_token`, and readiness settings do not
exist.

- [ ] **Step 3: Implement validated production settings**

Add these fields to `Settings`:

```python
port: int = 8000
app_admin_token: SecretStr
whatsapp_poll_interval: float = 1.0
whatsapp_retry_base_seconds: float = 2.0
whatsapp_retry_max_seconds: float = 60.0
max_request_bytes: int = 1_048_576
```

Reject blank `APP_ADMIN_TOKEN`, ports outside `1..65535`, and non-positive
retry/size values. Keep `_env_file=None` usable in tests so repository `.env`
does not leak into isolated test settings.

- [ ] **Step 4: Run configuration tests**

Run: `.venv/bin/pytest tests/test_config.py tests/test_readiness.py -q`

Expected: PASS.

### Task 2: Persist WhatsApp polling offsets securely

**Files:**
- Modify: `app/memory.py`
- Modify: `tests/test_memory.py`
- Modify: `app/whatsapp.py`
- Modify: `tests/test_whatsapp.py`

- [ ] **Step 1: Write failing offset tests**

```python
def test_poll_offset_survives_store_recreation(tmp_path):
    first = MemoryStore(tmp_path / "memory.db", "secret")
    assert first.get_offset() == 0
    first.save_offset(1287)
    second = MemoryStore(tmp_path / "memory.db", "secret")
    assert second.get_offset() == 1287
```

```python
def test_adapter_reads_and_saves_offset_from_memory(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db", "secret")
    adapter = OfficialWhatsAppAdapter(settings_with_key(), memory)
    assert adapter.offset == 0
    adapter.update_offset(17)
    assert memory.get_offset() == 17
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/pytest tests/test_memory.py tests/test_whatsapp.py -q`

Expected: FAIL because offset methods and adapter memory injection do not exist.

- [ ] **Step 3: Implement encrypted offset storage**

Add an encrypted `kv_memory` category named `whatsapp_offset` with:

```python
def get_offset(self) -> int: ...
def save_offset(self, offset: int) -> None: ...
```

Validate non-negative integer offsets and write transactionally. Change
`OfficialWhatsAppAdapter(settings, memory)` to load the offset at construction
and save `next_offset` immediately after a successful updates response.

- [ ] **Step 4: Run offset tests**

Run: `.venv/bin/pytest tests/test_memory.py tests/test_whatsapp.py -q`

Expected: PASS, including a fresh adapter continuing at the saved offset.

### Task 3: Harden FastAPI lifecycle, auth, readiness, and worker retries

**Files:**
- Modify: `app/api.py`
- Modify: `app/main.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Write failing endpoint and worker tests**

```python
def test_admin_endpoint_rejects_missing_token(tmp_path):
    app = create_test_app(tmp_path, admin_token="admin")
    response = TestClient(app).get("/memory/export")
    assert response.status_code == 401


def test_admin_endpoint_accepts_correct_token(tmp_path):
    app = create_test_app(tmp_path, admin_token="admin")
    response = TestClient(app).get(
        "/memory/export",
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 200


def test_readyz_reports_missing_ollama_configuration(tmp_path):
    app = create_test_app(tmp_path, admin_token="admin", ollama_api_key=None)
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
```

```python
@pytest.mark.asyncio
async def test_worker_backoff_does_not_spin_on_provider_error():
    worker = WorkerHarness(always_fail=True)
    await worker.run_once()
    assert worker.sleep_calls == [2.0]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/pytest tests/test_api.py tests/test_worker.py -q`

Expected: FAIL because admin authentication, readiness validation, and worker
backoff harness do not exist.

- [ ] **Step 3: Implement shared admin authentication**

Create a FastAPI dependency that requires:

```http
Authorization: Bearer <APP_ADMIN_TOKEN>
```

Apply it to `/messages`, `/webhooks/whatsapp`, `/agent/poll`,
`/memory/export`, and `/memory/forget/{category}`. Do not compare or log the
token in plaintext; use constant-time comparison. Keep `/healthz` and
`/readyz` unauthenticated so the platform can probe them.

- [ ] **Step 4: Implement readiness and platform port handling**

`/readyz` must return HTTP 200 only when:

- `MEMORY_KEY` and `APP_ADMIN_TOKEN` are non-blank.
- The memory database can be opened and queried.
- When WhatsApp is enabled, `WHATSAPP_API_KEY` and endpoint are configured.
- When Ollama-backed responses are enabled, `OLLAMA_API_KEY` is configured.

Return `503` with a generic list of missing configuration names; never return
secret values. Start Uvicorn using `settings.port` or the platform `$PORT`.

- [ ] **Step 5: Refactor the worker into bounded retry behavior**

Keep exactly one lifespan-created task. On each loop:

```python
delay = settings.whatsapp_retry_base_seconds
try:
    messages = await adapter.receive(limit=50, timeout=25)
    await process_messages(messages)
    delay = settings.whatsapp_retry_base_seconds
except transient_error:
    logger.warning("WhatsApp worker retry scheduled")
    await asyncio.sleep(delay)
    delay = min(delay * 2, settings.whatsapp_retry_max_seconds)
```

Reset the delay after a successful poll. Catch cancellation separately and
re-raise it so shutdown is immediate. Ensure a worker error cannot terminate
the web process.

- [ ] **Step 6: Run API and worker tests**

Run: `.venv/bin/pytest tests/test_api.py tests/test_worker.py -q`

Expected: PASS with unauthorized requests rejected, readiness accurate, and
worker retries bounded.

### Task 4: Add deployment manifests and production Docker behavior

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Create: `render.yaml`
- Create: `railway.toml`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Write manifest validation checks**

```python
def test_render_manifest_is_single_replica_with_health_path():
    data = yaml.safe_load(Path("render.yaml").read_text())
    service = data["services"][0]
    assert service["type"] == "web"
    assert service["healthCheckPath"] == "/healthz"
    assert service["numInstances"] == 1


def test_railway_manifest_uses_platform_port():
    text = Path("railway.toml").read_text()
    assert "healthcheckPath = \"/healthz\"" in text
```

- [ ] **Step 2: Run manifest tests and verify failure**

Run: `.venv/bin/pytest tests/test_deployment_manifests.py -q`

Expected: FAIL because the Render and Railway manifests do not exist.

- [ ] **Step 3: Add Render blueprint**

Create `render.yaml` with one Docker web service:

```yaml
services:
  - type: web
    name: personal-whatsapp-agent
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .
    healthCheckPath: /healthz
    numInstances: 1
    disk:
      name: agent-data
      mountPath: /app/data
      sizeGB: 1
```

Declare secret names as dashboard-managed values, not literals. Document that
the free/ephemeral plan must not be used if it cannot provide persistent disk.

- [ ] **Step 4: Add Railway configuration**

Create `railway.toml`:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/healthz"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
numReplicas = 1
```

Document the Railway volume mount `/app/data` and one-replica requirement in
README because volume provisioning is dashboard/project specific.

- [ ] **Step 5: Harden Docker and Compose**

Update `Dockerfile` to set `PYTHONUNBUFFERED=1`, use platform `${PORT:-8000}`,
run as `agent`, create `/app/data`, and include a healthcheck that calls
`/healthz`. Keep build context free of `.env`, `data`, caches, and test output.

Update Compose with `./data:/app/data`, `env_file: .env`, one service, health
check, and port `${PORT:-8000}:8000`.

- [ ] **Step 6: Run manifest and build checks**

Run:

```bash
.venv/bin/pytest tests/test_deployment_manifests.py -q
docker compose config
docker build -t personal-agent:local .
```

Expected: manifest tests pass, Compose renders valid YAML, and the production
image builds.

### Task 5: Document Render/Railway deployment and operational procedures

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/deployment.md`

- [ ] **Step 1: Add the complete secret/configuration matrix**

Document:

```text
MEMORY_KEY             required secret
APP_ADMIN_TOKEN        required secret
OLLAMA_API_KEY         required secret
WHATSAPP_API_KEY       required secret
OLLAMA_BASE_URL        https://ollama.com
OLLAMA_MODEL           gemma4:31b or configured supported model
WHATSAPP_ENABLED       true
WHATSAPP_ENDPOINT      https://api.whatsapp.com/agent/v1
WHATSAPP_AUTH_HEADER   Authorization
WHATSAPP_AUTH_SCHEME   Bearer
MEMORY_PATH            /app/data/memory.db
```

State explicitly that keys must be entered in the platform secret manager, not
committed or placed in Dockerfile/Compose YAML.

- [ ] **Step 2: Document Render deployment**

Give exact steps: connect repository, apply `render.yaml`, add four secrets,
attach persistent disk at `/app/data`, keep one instance, deploy, inspect
health/logs, and send a WhatsApp test message. Include restart/rollback steps
and a warning that removing the disk loses memory/offset state.

- [ ] **Step 3: Document Railway deployment**

Give exact steps: deploy from repository/Dockerfile, add service variables,
create and mount a volume at `/app/data`, configure health path `/healthz`,
set one replica, deploy, inspect logs, and send a WhatsApp test message.

- [ ] **Step 4: Document operational verification**

Include:

```bash
curl -fsS https://<deployment-host>/healthz
curl -fsS https://<deployment-host>/readyz
curl -fsS -H "Authorization: Bearer $APP_ADMIN_TOKEN" \
  https://<deployment-host>/memory/export
```

The final smoke test is a real message sent to the configured WhatsApp Agent;
verify one Roman Urdu reply and one worker instance in logs. Never paste keys
into shell history or issue descriptions.

### Task 6: Run full verification and deployment rehearsal

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `README.md` if command output differs

- [ ] **Step 1: Add deployment integration assertions**

```python
def test_protected_local_message_requires_admin_token(client):
    response = client.post("/messages", json=valid_message())
    assert response.status_code == 401


def test_health_is_public_and_ready_is_structured(client):
    assert client.get("/healthz").status_code == 200
    response = client.get("/readyz")
    assert response.status_code in {200, 503}
    assert "status" in response.json()
```

- [ ] **Step 2: Run the complete validation suite**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
docker compose config
docker build -t personal-agent:local .
```

Expected: all tests pass, Ruff is clean, Compose is valid, and the image
builds without copying `.env`, `data`, or test caches.

- [ ] **Step 3: Rehearse container startup**

Run with a temporary local `.env` containing test credentials:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/readyz
docker compose logs --no-color --tail=100 agent
docker compose down
```

Expected: the health endpoint returns 200, readiness identifies only missing
real provider credentials when test values are absent, logs contain no secret
values, and shutdown exits cleanly.

- [ ] **Step 4: Commit when a Git repository is available**

Run:

```bash
git add app tests Dockerfile docker-compose.yml render.yaml railway.toml \
  .env.example .gitignore README.md docs
git commit -m "chore: prepare agent for managed deployment"
```

If the current workspace remains outside Git, do not initialize or discard
history; retain the validated files and report that commit was skipped.

## Final acceptance checklist

- [ ] Single Docker web service and exactly one worker.
- [ ] Render and Railway manifests use `/healthz` and one replica.
- [ ] Persistent `/app/data` volume documented and configured.
- [ ] `MEMORY_KEY`, `APP_ADMIN_TOKEN`, `OLLAMA_API_KEY`, and
      `WHATSAPP_API_KEY` are managed secrets.
- [ ] `/readyz` reflects actual readiness.
- [ ] Admin endpoints reject missing/invalid tokens.
- [ ] Worker retries with bounded backoff and shuts down gracefully.
- [ ] WhatsApp offset persists across restart.
- [ ] Full tests, lint, Compose validation, and Docker build pass.
- [ ] Render/Railway deployment and real WhatsApp round-trip documented.
