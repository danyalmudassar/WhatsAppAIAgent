# Deployment

## Backend service

Run exactly one backend replica because the official WhatsApp Agent API uses
stateful long polling and persisted offsets. Mount the Railway volume at
`/app/data` and set `MEMORY_PATH=/app/data/memory.db`. Required secrets are
`MEMORY_KEY`, `APP_ADMIN_TOKEN`, `OLLAMA_API_KEY`, `WHATSAPP_API_KEY`, and
`OWNER_PASSWORD_HASH`. Set `DASHBOARD_ORIGIN` to the deployed dashboard URL.

The backend service is:

```text
https://whatsappaiagent-production-63d3.up.railway.app
```

## Optional decision router

Decision routing production chat generation ko replace nahi karti. Enable it
only after local smoke tests pass. On CPU-only hosts, install a CPU PyTorch
wheel before installing Laya so pip does not select CUDA runtime packages:

```bash
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.0'
.venv/bin/pip install -e '.[decision-local]' --no-deps
```

```env
DECISION_ROUTER_ENABLED=true
DECISION_BACKENDS=laya,openjev,jev
DECISION_TIMEOUT_SECONDS=2.0
DECISION_CONFIDENCE_THRESHOLD=0.75
LAYA_MODEL=convaiinnovations/laya-multilingual
OPENJEV_URL=https://api.codiv.ai
JEV_URL=
JEV_API_KEY=
```

The Jev-compatible `typesafe-sdk` is optional and can be installed with
`pip install -e '.[decision-jev]'`; local Jev weights are not part of this
project.

Keep Laya/OpenJev model dependencies in an isolated sidecar environment when
their packages are not part of the production image. Use one authenticated
decision endpoint and never pass backend credentials to Copilot, Antigravity,
or another coding agent. Treat `review_required=true` as a mandatory human
approval gate.

## Dashboard service

Deploy the `dashboard/` directory as a separate Railway service. Railway
provides port `8080`; the standalone Next.js image must retain both
`.next/standalone` and `.next/static`. The dashboard uses the backend origin
for authenticated API calls and stores encrypted conversations, agents,
providers, audit records, and settings in the backend volume.

Dashboard URL:

```text
https://agent-dashboard-production-10fc.up.railway.app
```

## Smoke checks

```bash
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/healthz
curl -fsS https://whatsappaiagent-production-63d3.up.railway.app/readyz
curl -I https://agent-dashboard-production-10fc.up.railway.app
```

After login, verify overview, agent/provider CRUD, provider connection test,
conversation history, chat, live activity, and audit. Never include provider
secrets in logs, screenshots, URLs, or support messages.

## GitHub Actions

The Railway workflow requires `RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, and a
backend `RAILWAY_SERVICE_ID`. Dashboard deployment is a separate service and
must use its own service ID/job; do not point both services at the backend
service. Keep the one-replica backend setting unchanged.
