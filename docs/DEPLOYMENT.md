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
