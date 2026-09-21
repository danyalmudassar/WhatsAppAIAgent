# Managed Agent Deployment Design

## Scope

Prepare the personal WhatsApp AI agent for an always-on managed deployment on
Render or Railway using one Docker web service. The service runs FastAPI and
one WhatsApp long-poll worker in the same process, uses Ollama Cloud, preserves
encrypted local memory on a managed persistent disk/volume, and restarts safely.

The deployment must remain single-replica because WhatsApp update offsets are
stateful and multiple pollers could process the same update. The existing
official WhatsApp Agent Platform API integration is retained; unofficial
WhatsApp automation is out of scope.

## Goals

- Deploy the current agent as one production Docker service on Render or
  Railway.
- Start the WhatsApp worker automatically with the web application.
- Keep `memory.db` and polling offset state on persistent encrypted storage.
- Store all credentials in managed platform secrets.
- Add readiness, graceful shutdown, retry/backoff, and safe error handling.
- Protect administrative and manual agent endpoints with an admin token.
- Provide reproducible deployment and verification instructions.

## Architecture

The container runs FastAPI/Uvicorn and one background WhatsApp long-poll worker.
The worker calls the documented `GET /agent/v1/updates` endpoint, routes text
messages through LangGraph and Ollama Cloud, then sends replies through
`POST /agent/v1/messages`. A single replica is required.

The platform exposes `/healthz` for process health and `/readyz` for
configuration/readiness. A managed persistent disk/volume is mounted at
`/app/data`, where the encrypted SQLite database and polling offset state live.
The container runs as a non-root user.

## Configuration and secrets

Required managed secrets:

- `MEMORY_KEY`
- `OLLAMA_API_KEY`
- `WHATSAPP_API_KEY`
- `APP_ADMIN_TOKEN`

Required non-secret configuration includes:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `WHATSAPP_ENABLED`
- `WHATSAPP_ENDPOINT`
- `WHATSAPP_AUTH_HEADER`
- `WHATSAPP_AUTH_SCHEME`
- `MEMORY_PATH`
- `PORT` supplied by the platform

No real credential may be committed, copied into an image, returned in a
response, or emitted in logs.

## Production hardening

- `/readyz` checks required configuration and memory-store availability.
- WhatsApp and Ollama failures use bounded retries and exponential backoff.
- The worker starts once per process and is cancelled during graceful shutdown.
- Polling offsets are persisted so restarts do not intentionally skip updates.
- One-replica deployment is documented and represented in deployment manifests.
- CORS is disabled by default and debug mode is not enabled.
- Docker runs as non-root and supports a mounted data directory.
- Request body limits and admin authentication protect sensitive endpoints.
- `/memory/export`, `/memory/forget/*`, `/messages`, and manual `/agent/poll`
  require `APP_ADMIN_TOKEN`; `/healthz` and `/readyz` are read-only.
- Error responses are generic and never include provider response bodies or
  secrets.

## Deployment artifacts

The implementation will maintain:

- A production-compatible `Dockerfile`.
- `docker-compose.yml` for local production-like verification.
- `render.yaml` for a one-service Render blueprint with disk and health path.
- Railway deployment configuration/instructions with one service and volume.
- `.env.example` with placeholders only.
- README instructions for secrets, deployment, logs, restart, rollback, and
  WhatsApp round-trip verification.

## Testing and verification

Automated tests cover:

- Admin-token protection and unauthorized endpoint rejection.
- Configuration validation and readiness failure states.
- Exactly-one worker startup and graceful lifespan shutdown.
- Backoff/retry behavior and empty poll responses.
- Duplicate update handling and persistent offset behavior.
- Existing graph, memory, tool, API, and WhatsApp adapter behavior.

Verification commands:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
docker build -t personal-agent:local .
docker compose config
```

After deployment, verify `/healthz`, `/readyz`, platform logs, one active
worker, persistent data after restart, and a real WhatsApp message round-trip.

## Acceptance criteria

- Render or Railway can build and start the service with platform `$PORT`.
- Health and readiness checks pass only when the service is usable.
- Exactly one WhatsApp polling worker runs in the deployed process.
- A WhatsApp message receives a Roman Urdu reply through Ollama Cloud.
- Restart preserves encrypted memory and polling state.
- Administrative endpoints reject requests without the admin token.
- Secrets are absent from source, image layers, logs, and error responses.
- Deployment documentation supports both Render and Railway.
