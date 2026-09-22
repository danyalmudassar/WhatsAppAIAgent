# Agent Control Center Dashboard Design

**Date:** 2026-09-22  
**Status:** Approved concept; implementation pending written-spec review

## Goal

Build a customizable Next.js + TypeScript dashboard for the deployed FastAPI
agent. The dashboard combines an operations control center with an agent
workspace. It must show realtime runtime activity, provide a chat console,
support controlled runtime configuration, and establish a provider-agnostic
foundation for future MCP and skills management.

The first phase covers dashboard operations and Agent Studio foundation.
MCP/skills installation and lifecycle management are explicitly deferred to a
follow-up phase, but the backend contracts must leave room for them.

## Product scope

### Operations Control Center

- Overview of service, WhatsApp worker, memory store, and model-provider health.
- Realtime incoming/outgoing message and runtime event stream.
- Error visibility with safe, redacted details.
- Manual worker status/restart controls with confirmation.
- Recent event history after browser reconnect.

### Agent Workspace

- Create, edit, select, and disable named agents.
- Configure system prompt, response language, memory profile, enabled tools,
  provider priority, and fallback behavior.
- Start, stop, and restart an agent with explicit confirmation.
- Preview effective configuration before applying changes.

### Chat Console

- Select an agent and send a dashboard message.
- Stream assistant output and runtime events.
- Show conversation history and delivery/result status.
- Keep dashboard chat separate from WhatsApp polling state.

### Providers

Use a common provider adapter interface. The architecture must support:

- Ollama Cloud and local Ollama.
- OpenAI-compatible HTTP endpoints.
- Native OpenAI, Anthropic, Gemini, and Azure adapters later.
- Custom adapters without changing LangGraph routing.

Phase-one production adapters are Ollama and OpenAI-compatible endpoints.
Provider credentials, API keys, and headers are encrypted at rest and masked
in all responses and logs.

### Authentication

- Login with a single owner account in phase one.
- Secure, HttpOnly, SameSite session cookie.
- Session expiry and logout.
- Server-side authorization boundary designed for future owner/operator/viewer
  roles.
- Dashboard APIs reject unauthenticated requests.

## Architecture

The existing FastAPI service remains the control plane and the only process
allowed to run the WhatsApp long-poll worker. Next.js is a separate dashboard
frontend in the same Railway project. It communicates with FastAPI through
authenticated HTTP APIs and one realtime stream.

```text
Browser (Next.js)
  ├── authenticated REST requests ──> FastAPI control API
  └── SSE/WebSocket stream ──────────> FastAPI event gateway
                                           ├── Agent registry/config
                                           ├── LangGraph runtime
                                           ├── provider adapters
                                           ├── encrypted memory/config store
                                           └── single WhatsApp worker
```

The browser must never receive provider secrets, Fernet keys, raw bearer
tokens, or unrestricted filesystem access.

## Backend boundaries

### Configuration and registry

Persist versioned records for agents and providers. Each configuration update
creates an audit event and increments a revision. Runtime reads a consistent
revision; applying an edit either succeeds atomically or returns a validation
error without changing the active revision.

Suggested resource boundaries:

- `ProviderConfig`: id, type, display name, base URL, model, encrypted secret
  reference, timeout, enabled, priority.
- `AgentConfig`: id, name, system prompt, language, memory profile, tool allow
  list, provider priority, enabled, revision.
- `Session`: id, owner, created/last-used timestamps, expiry, revocation state.
- `RuntimeEvent`: id, timestamp, type, agent id, correlation id, redacted
  payload, severity.
- `AuditEvent`: id, actor, action, resource, revision, timestamp, result.

Secrets are stored as encrypted values in the existing protected storage
boundary. They are write-only through the API: the UI can show presence and
last-four metadata, never the secret itself.

### API surface

The phase-one contract uses these paths:

- `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`.
- `GET /dashboard/overview`, `GET /dashboard/events`.
- CRUD and apply/validate endpoints for agents and providers.
- `POST /dashboard/chat` with streamed or correlation-based response.
- `POST /dashboard/runtime/restart` and safe worker status endpoint.
- `GET /dashboard/events/stream` using SSE initially; WebSocket is reserved
  for a future bidirectional-control upgrade.

All mutating endpoints validate input, require an authenticated session, emit
an audit event, and return a safe structured error on failure. Health endpoints
remain suitable for Railway and do not expose secrets or private event data.

### Event lifecycle

Emit events for `message_received`, `agent_routed`, `model_started`,
`tool_called`, `response_ready`, `message_sent`, `config_changed`, and `error`.
Each event carries a correlation id. Persist only redacted metadata and
bounded content; never persist API keys or unrestricted raw prompt content by
default.

SSE sends an initial snapshot, then ordered events, heartbeat comments, and a
reconnect cursor. If an event is too old or unavailable, the client receives a
fresh snapshot instead of silently showing an incomplete timeline.

## Runtime controls and safety

- Provider/model changes apply to new requests by default.
- Restart is explicit and requires confirmation.
- Agent disable prevents new dashboard/WhatsApp routing but does not interrupt
  an already-running request.
- Tool permissions use an allow list and preserve existing destructive-action
  confirmation policies.
- Configuration preview shows changed fields, redacted secrets, and expected
  runtime impact before apply.
- Audit events are append-only from the application API.
- Dashboard chat cannot invoke unrestricted deployment, shell, or credential
  operations.

## Frontend structure

Next.js + TypeScript uses a shared authenticated app shell:

- `Overview`: status cards and recent event timeline.
- `Live Activity`: filterable realtime event feed.
- `Chat Console`: agent selector, transcript, streaming response.
- `Agents`: registry and configuration editor.
- `Providers`: provider setup, masked credential state, connection test.
- `Settings`: language, memory, polling, session, and workspace controls.
- `Audit Log`: immutable change history.

The UI must expose loading, empty, stale-stream, unauthorized, validation,
and degraded-worker states. Destructive or operational actions use explicit
confirmation and visible success/failure feedback.

## MCP and skills extension point

MCP servers and skills are not part of phase one. The provider/tool registry
must nevertheless use capability descriptors and permission boundaries so a
later MCP/skills phase can add:

- registered MCP server metadata and connection status;
- skill manifest, version, enabled state, and required permissions;
- per-agent capability allow lists;
- install/update/remove audit events.

No arbitrary package installation or remote code execution is allowed through
the phase-one dashboard.

## Deployment

Keep the existing Railway backend service as the single WhatsApp worker.
Deploy the Next.js dashboard as a separate Railway service with its own
public route. Configure the frontend with only the backend public API origin,
never backend secrets. Use HTTPS, secure cookies, and one backend replica.
Persistent encrypted data remains on the backend `/app/data` volume.

CI must run frontend and backend lint, tests, type checks, and production
builds before deployment. Dashboard deployment must not change the existing
WhatsApp worker replica rule.

## Testing and acceptance criteria

### Backend

- Unauthenticated dashboard requests return 401.
- Login, expiry, logout, and revoked sessions work.
- Provider secrets are encrypted and never returned in API payloads/logs.
- Agent/provider validation and atomic revision updates work.
- Runtime events are redacted, bounded, correlated, persisted, and streamed.
- Restart and provider changes require authorization and create audit events.
- Existing WhatsApp polling, offset persistence, Roman Urdu responses, and
  duplicate-delivery behavior remain passing.

### Frontend

- Protected routes redirect to login.
- Overview displays health and degraded states.
- Activity feed reconnects with a cursor and does not duplicate events.
- Chat console streams responses and shows errors safely.
- Agent/provider editors validate, preview, apply, and refresh revisions.
- Sensitive controls require confirmation.

### Deployment

- Backend and dashboard images build in CI.
- Railway health checks pass for both services.
- Backend has one replica and persistent `/app/data`.
- No production secret appears in Git, CI output, browser payloads, or logs.
- A manual smoke test can log in, inspect live status, change a non-secret
  setting, send a dashboard chat message, and observe the corresponding
  realtime events.

## Explicit non-goals for phase one

- MCP server installation and arbitrary skill execution.
- Multi-user role administration.
- Browser-based shell or unrestricted filesystem management.
- Automatic provider discovery or billing/quota management.
- Replacing WhatsApp's official personal Agent API.
