# Agent Control Center Full Functionality

## Goal

Make the deployed dashboard a functional operations and agent workspace rather than a read-only status page. The dashboard must support agent and provider management, persistent conversations, streaming chat, realtime operations, and auditable configuration changes without disrupting the single WhatsApp polling worker.

## Constraints and decisions

- Keep the existing FastAPI backend, Next.js client, and encrypted SQLite store on the Railway persistent volume.
- Keep WhatsApp polling isolated to one backend replica.
- Use the operation-first dashboard layout.
- Use cookie sessions and the existing authenticated dashboard routes.
- Never return provider secrets; accept them only on write, encrypt them at rest, and use them only for outbound provider requests.
- Deliver the work as incremental vertical slices so each slice can be tested and deployed independently.

## Architecture and data flow

The encrypted SQLite store remains the source of truth for providers, agents, conversations, messages, runtime events, and audit records. Typed service boundaries sit between the FastAPI routes and the store:

1. Agent commands validate input, enforce optimistic `revision` checks, and persist changes.
2. Provider commands validate configuration, encrypt replacement secrets, expose only masked metadata, and resolve enabled providers by priority.
3. Chat commands create or resume durable sessions, persist user and assistant messages, resolve an agent and provider, and emit redacted lifecycle events.
4. Provider failures are normalized and passed to the fallback resolver. A provider that cannot stream uses the non-streaming path.
5. SSE delivers live runtime events and chat chunks; persisted messages remain authoritative if a browser disconnects.
6. Every configuration mutation and chat lifecycle transition writes an audit record with safe metadata.

## Backend components

### Agent service

Provide create, update, list, and delete operations for agent name, system prompt, tools, memory profile, response language, enabled state, and provider priority. Updates require the caller's current revision and return a conflict on stale writes.

### Provider service

Provide create, update, list, delete, connection-test, and priority operations for Ollama and OpenAI-compatible providers. Store secrets encrypted, expose `has_secret` and last-four metadata only, send real bearer credentials on outbound requests, and never include credentials in exceptions, events, or audit records. Connection tests use bounded timeouts and return an explicit normalized error.

### Chat service

Add durable conversation and message records. A request identifies an optional conversation and agent; otherwise the service creates a conversation and uses the default enabled agent. The service attempts providers in configured priority order, persists the user message before invocation, persists the assistant response after completion, and records provider/fallback outcomes. Streaming providers emit chunks over SSE; non-streaming providers return one completed response.

### Operations service

Expose runtime status, paginated events and audit records, settings needed by the dashboard, and explicit controls for safe runtime actions. Destructive actions require confirmation in the UI and are protected by the same authenticated route boundary.

## Frontend behavior

The Next.js dashboard uses an operation-first navigation shell:

- **Overview:** health, WhatsApp worker state, provider/agent counts, and current errors.
- **Chat:** conversation history, new conversation, agent selection, message persistence, streaming response state, provider/fallback status, retry, and error recovery.
- **Agents:** editor for prompt, tools, memory profile, language, enabled state, and provider priority; save conflicts prompt a reload.
- **Providers:** editor for type, endpoint, model, secret, enabled state, priority, connection test, and delete confirmation.
- **Live Activity:** reconnecting SSE feed with clear disconnected state.
- **Audit:** paginated mutation and chat lifecycle history with safe metadata.
- **Settings:** non-secret dashboard/runtime settings and safe action confirmations.

All screens have explicit loading, empty, validation, unauthorized, conflict, and server-error states. The frontend never assumes a successful response shape when the API returns an error.

## Error handling and safety

- `401` clears the local authenticated state and returns to login.
- `409` preserves unsaved form input and asks the user to reload the latest revision.
- Provider failures identify the attempted provider and whether a fallback was selected, without exposing secrets.
- SSE disconnects show a reconnect state and retain persisted messages/events.
- Timeouts and upstream errors use bounded retries only where the existing provider policy permits; otherwise they surface clearly.
- Audit and runtime event payloads are redacted before persistence.

## Verification

Backend tests will cover encrypted conversation/message round trips, agent/provider CRUD, revision conflicts, secret masking, provider bearer headers, connection-test errors, priority fallback, chat persistence, streaming/non-streaming behavior, event/audit emission, and auth expiry. Frontend checks will include strict TypeScript, ESLint, production build, and focused component/request behavior where the project test setup supports it. Deployment smoke verification will exercise login, agent/provider CRUD, provider test, chat history, SSE activity, audit retrieval, health, and readiness while confirming the WhatsApp worker remains single-replica.

## Delivery slices

1. Agent Studio and Provider Manager CRUD, connection tests, priority resolution, and tests.
2. Persistent conversations, history, provider-backed chat, streaming events, and tests.
3. Operations controls, complete lifecycle event wiring, settings/audit pagination, UI confirmation flows, deployment smoke checks, and documentation.
