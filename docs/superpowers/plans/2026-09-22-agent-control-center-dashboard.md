# Agent Control Center Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure Next.js dashboard and FastAPI control-plane foundation for realtime monitoring, chat, agent configuration, and model-provider switching.

**Architecture:** Keep the existing FastAPI service as the only WhatsApp worker and add authenticated control APIs, encrypted configuration storage, audit/event persistence, provider adapters, and SSE. Add a separate Next.js TypeScript dashboard service that uses HttpOnly sessions and the FastAPI API; MCP and skills remain extension points, not phase-one installers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite/Fernet, LangGraph, httpx, Next.js, TypeScript, React, SSE, Docker, Railway, pytest, Ruff, ESLint, TypeScript compiler.

---

## File map

- Modify `app/config.py`: dashboard/session and event settings.
- Create `app/dashboard_models.py`: typed provider, agent, session, event, and audit contracts.
- Create `app/dashboard_store.py`: SQLite schema and encrypted secret/config persistence.
- Create `app/auth.py`: password verification, session creation, cookie helpers, expiry/revocation.
- Create `app/events.py`: bounded redacted event records, cursor reads, and SSE formatting.
- Create `app/providers.py`: provider adapter protocol, Ollama adapter, OpenAI-compatible adapter, and registry.
- Modify `app/graph.py`: resolve an agent configuration and provider adapter without changing existing routing behavior.
- Modify `app/api.py`: authenticated dashboard routes, SSE stream, chat control, runtime/config actions, and event emission.
- Modify `app/whatsapp.py`: emit message lifecycle events through an injected event sink.
- Create `tests/test_dashboard_store.py`, `tests/test_auth.py`, `tests/test_events.py`, `tests/test_providers.py`, and extend `tests/test_api.py`/`tests/test_whatsapp.py`.
- Create `dashboard/`: Next.js app with authenticated layout, pages for overview/activity/chat/agents/providers/settings/audit, typed API client, SSE hook, and UI components.
- Modify `Dockerfile` only for backend compatibility if needed; create `dashboard/Dockerfile`.
- Modify `.github/workflows/ci.yml` and `.github/workflows/deploy-railway.yml` for backend/frontend quality gates and dashboard deployment.
- Modify `railway.toml` or add Railway service configuration documentation for a separate dashboard service.
- Modify `.env.example` and `README.md` with dashboard origin, owner credentials, session settings, and deployment steps.

## Task 1: Add dashboard configuration and domain contracts

**Files:** `app/config.py`, `app/dashboard_models.py`, `tests/test_config.py`, `tests/test_dashboard_models.py`

- [ ] **Step 1: Write failing settings/model tests.** Test `DASHBOARD_ORIGIN`, session TTL, event retention, owner username/password hash, and validation of provider type, agent name, and revision.
- [ ] **Step 2: Run `.venv/bin/pytest tests/test_config.py tests/test_dashboard_models.py -q`; verify the new fields/imports fail.**
- [ ] **Step 3: Add typed Pydantic models:** `ProviderType`, `ProviderConfig`, `AgentConfig`, `SessionRecord`, `RuntimeEvent`, `AuditEvent`, `ConfigRevision`, and safe response models that omit secrets.
- [ ] **Step 4: Add settings fields `dashboard_origin`, `session_ttl_seconds`, `event_retention`, `owner_username`, and `owner_password_hash`; reject blank values and non-positive limits.**
- [ ] **Step 5: Run the targeted tests and commit `feat: add dashboard contracts and settings`.**

## Task 2: Persist encrypted dashboard state

**Files:** `app/dashboard_store.py`, `tests/test_dashboard_store.py`, `app/memory.py`

- [ ] **Step 1: Write tests for provider secret encryption, agent revisions, sessions, cursored events, and append-only audit records.**
- [ ] **Step 2: Verify tests fail because `DashboardStore` does not exist.**
- [ ] **Step 3: Implement SQLite tables `providers`, `agents`, `dashboard_sessions`, `runtime_events`, and `audit_events`; encrypt provider secrets and private config values with the existing `EncryptedCodec`.**
- [ ] **Step 4: Implement atomic `save_provider`, `save_agent`, `create_session`, `revoke_session`, `append_event`, `events_after(cursor)`, and `append_audit`; return redacted DTOs only.**
- [ ] **Step 5: Verify ciphertext does not contain plaintext secrets and revision conflicts leave the active record unchanged.**
- [ ] **Step 6: Run targeted store tests and commit `feat: persist encrypted dashboard state`.**

## Task 3: Add secure login sessions

**Files:** `app/auth.py`, `app/api.py`, `tests/test_auth.py`, `tests/test_api.py`

- [ ] **Step 1: Write tests for valid login, invalid credentials, cookie attributes, expiry, logout, revoked sessions, and unauthenticated dashboard access.**
- [ ] **Step 2: Verify the tests fail.**
- [ ] **Step 3: Implement password-hash verification using the project’s installed cryptography primitives, opaque random session IDs stored hashed in SQLite, and `HttpOnly`, `Secure`, `SameSite=Lax` cookies.**
- [ ] **Step 4: Add `POST /auth/login`, `POST /auth/logout`, and `GET /auth/session`; use one owner account while keeping an actor/role field for future roles.**
- [ ] **Step 5: Add a dependency/helper that rejects missing, expired, or revoked sessions with 401.**
- [ ] **Step 6: Run auth/API tests and commit `feat: add dashboard session authentication`.**

## Task 4: Add event bus and realtime SSE

**Files:** `app/events.py`, `app/api.py`, `tests/test_events.py`, `tests/test_api.py`

- [ ] **Step 1: Write tests for redaction, payload-size bounds, correlation IDs, cursor ordering, initial snapshot, heartbeat, and reconnect behavior.**
- [ ] **Step 2: Verify tests fail.**
- [ ] **Step 3: Implement an `EventRecorder` that writes bounded redacted events to `DashboardStore` and broadcasts them to per-process async subscribers.**
- [ ] **Step 4: Implement `GET /dashboard/events/stream` as an authenticated `StreamingResponse` with `Last-Event-ID`/cursor support, initial snapshot, SSE `id`, `event`, and `data` fields, and periodic heartbeat comments.**
- [ ] **Step 5: Ensure API keys, bearer tokens, Fernet keys, raw authorization headers, and unbounded message/prompt bodies are redacted or truncated before persistence/streaming.**
- [ ] **Step 6: Run event/API tests and commit `feat: stream realtime dashboard events`.**

## Task 5: Implement model-provider adapters

**Files:** `app/providers.py`, `app/llm.py`, `app/graph.py`, `tests/test_providers.py`, `tests/test_graph.py`

- [ ] **Step 1: Write adapter contract tests for Ollama, OpenAI-compatible chat, timeout/error normalization, provider priority, and fallback selection.**
- [ ] **Step 2: Verify tests fail.**
- [ ] **Step 3: Define `ChatProvider` with `generate`, `stream`, `health`, and safe metadata methods; implement Ollama using existing settings and OpenAI-compatible using `httpx` without exposing secrets.**
- [ ] **Step 4: Implement a registry that loads enabled providers from `DashboardStore`, selects the requested agent’s priority list, and tries the next provider only for retryable provider failures.**
- [ ] **Step 5: Preserve the current default graph behavior when no dashboard agent is selected, and emit `model_started`, `response_ready`, and provider-error events.**
- [ ] **Step 6: Run provider/graph tests and commit `feat: add pluggable model providers`.**

## Task 6: Add dashboard control APIs

**Files:** `app/api.py`, `app/whatsapp.py`, `tests/test_api.py`, `tests/test_whatsapp.py`

- [ ] **Step 1: Write tests for overview, event history, agent/provider CRUD, validation preview, atomic apply, chat response, runtime status/restart authorization, audit records, and safe errors.**
- [ ] **Step 2: Verify tests fail.**
- [ ] **Step 3: Add authenticated routes `/dashboard/overview`, `/dashboard/events`, `/dashboard/chat`, `/dashboard/agents`, `/dashboard/providers`, `/dashboard/runtime`, and `/dashboard/audit`.**
- [ ] **Step 4: Inject the event recorder into WhatsApp receive/process/send paths and emit message lifecycle events with correlation IDs.**
- [ ] **Step 5: Require explicit confirmation fields for restart, disable, provider switch, and destructive changes; reject stale config revisions with 409.**
- [ ] **Step 6: Run all backend tests and commit `feat: expose dashboard control APIs`.**

## Task 7: Scaffold the Next.js dashboard

**Files:** `dashboard/package.json`, `dashboard/tsconfig.json`, `dashboard/next.config.ts`, `dashboard/app/**`, `dashboard/components/**`, `dashboard/lib/**`

- [ ] **Step 1: Create the Next.js TypeScript app with strict TypeScript, ESLint, and a minimal accessible design system; do not add secrets to frontend build variables.**
- [ ] **Step 2: Add typed API client methods for auth, overview, events, agents, providers, chat, runtime, and audit routes.**
- [ ] **Step 3: Implement login page and protected app layout; redirect unauthenticated users to `/login`, and provide logout/session-expired handling.**
- [ ] **Step 4: Implement Control Center pages: Overview status cards, Live Activity event feed, and Audit Log with loading/empty/degraded states.**
- [ ] **Step 5: Implement Agent Workspace pages: Chat Console, Agents editor, Providers editor/test connection, and Settings.**
- [ ] **Step 6: Add an SSE hook that reconnects with the latest cursor, deduplicates event IDs, and marks the stream stale without hiding existing events.**
- [ ] **Step 7: Run `npm run lint`, `npx tsc --noEmit`, and `npm run build`; commit `feat: add agent control center dashboard`.**

## Task 8: Integrate deployment and CI

**Files:** `dashboard/Dockerfile`, `.github/workflows/ci.yml`, `.github/workflows/deploy-railway.yml`, `railway.toml`, `.env.example`, `README.md`

- [ ] **Step 1: Add a multi-stage dashboard Dockerfile that accepts only `NEXT_PUBLIC_API_ORIGIN` and runs as non-root.**
- [ ] **Step 2: Extend CI with dashboard dependency install, lint, strict type check, test command, and production build; keep backend gates unchanged.**
- [ ] **Step 3: Add a separate Railway dashboard service using the GitHub repository, public API origin, HTTPS cookie configuration, health path, and one dashboard replica.**
- [ ] **Step 4: Document Railway variables, backend CORS/origin configuration, dashboard URL, session secret handling, rollback, and the single-backend-replica WhatsApp rule.**
- [ ] **Step 5: Run Docker builds and `railway` configuration validation without printing secrets; commit `chore: deploy dashboard service`.**

## Task 9: End-to-end verification

**Files:** `tests/test_e2e_contracts.py`, `dashboard/tests/**`, `README.md`

- [ ] **Step 1: Add backend contract tests covering login → overview → SSE → chat → audit flow with a fake provider and no external API calls.**
- [ ] **Step 2: Add frontend tests for protected routing, event deduplication, provider secret masking, and confirmation dialogs.**
- [ ] **Step 3: Run `.venv/bin/pytest -q`, `.venv/bin/ruff check .`, backend compile checks, dashboard lint/type/build, and both Docker builds.**
- [ ] **Step 4: Deploy to a non-production Railway environment or controlled service revision; verify `/healthz`, `/readyz`, dashboard login, live events, chat, provider test, and rollback.**
- [ ] **Step 5: Confirm no secrets occur in Git diff, CI logs, browser payloads, or application logs; commit `test: verify dashboard end to end`.**

## Self-review checklist

- Authentication, encrypted secrets, redaction, audit, SSE cursors, provider fallback, UI pages, CI, deployment, and acceptance criteria each map to a task.
- No MCP/skills installer is included in phase one; only registry/capability extension points are planned.
- WhatsApp remains one backend replica and dashboard chat does not share polling offsets.
- Provider names and method signatures are consistent across Tasks 1, 2, 5, and 6.
- Every mutating action has validation, authorization, audit emission, and explicit confirmation where required.
