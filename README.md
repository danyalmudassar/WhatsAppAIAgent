# Personal WhatsApp AI Agent

Yeh local-first LangChain/LangGraph agent hai jo Ollama Cloud ko primary model
ke taur par use karta hai, encrypted local SQLite memory rakhta hai, aur Roman
Urdu mein jawab deta hai.

## Response language

Agent responses natural, balanced Roman Urdu mein Latin script mein aati hain.
Zaroori technical terms, product names, commands, URLs, filenames, identifiers,
error codes aur API names English mein rehne dene chahiyein jab is se jawab
clear aur direct banta hai. Output ko automatic translation ya meaning-changing
post-processing ke zariye modify nahi kiya jata.

## Local setup

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
mkdir -p data
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generated key ko `.env` ke `MEMORY_KEY` mein rakhein aur `OLLAMA_API_KEY`
mein apni Ollama Cloud key set karein. Secrets ko git mein commit na karein.

## System One decision router

Decision models routing aur risk decisions ke liye optional layer hain; Ollama
abhi bhi conversational Roman Urdu response generate karta hai. Local Laya
install aur CPU smoke test:

```bash
.venv/bin/pip install -e '.[decision-local]'
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python scripts/test_laya.py
```

OpenJev ko separate environment ya HTTP service ke taur par test karein:

```bash
.venv/bin/python scripts/test_openjev.py --mock
OPENJEV_URL=http://127.0.0.1:PORT .venv/bin/python scripts/test_openjev.py
```

Benchmark output hamesha `local`, `mock`, ya `live` mode label karta hai:

```bash
.venv/bin/python scripts/benchmark_decisions.py --iterations 10 --mock
```

Jev closed-source remote backend hai; local weights install nahi hoti. Live Jev
test ke liye `JEV_URL` aur `JEV_API_KEY` explicitly configure karna hoga.
Decision router unavailable ho to agent fabricated confidence nahi banata aur
high-risk/ambiguous requests ko review ke liye mark karta hai. Coding-agent
MCP aur HTTP examples `docs/decision-router-agents.md` mein hain.

## Run and test

```bash
.venv/bin/pytest -q
.venv/bin/uvicorn app.main:app --reload
```

`POST /messages` local testing ke liye hai. Official WhatsApp Agent ke liye
Uvicorn startup par background polling worker automatically start hota hai.
Manual testing ke liye `POST /agent/poll` endpoint bhi available hai.

## Official WhatsApp personal Agent

Attached WhatsApp Agent Platform Developer Manual ke mutabiq `.env` mein:

```env
WHATSAPP_ENABLED=true
WHATSAPP_API_KEY=apni_api_key
WHATSAPP_ENDPOINT=https://api.whatsapp.com/agent/v1
WHATSAPP_AUTH_HEADER=Authorization
WHATSAPP_AUTH_SCHEME=Bearer
```

Messages receive karne ke liye:

```bash
curl -X POST 'http://localhost:8000/agent/poll?limit=50&timeout=15'
```

Production/local server start karte hi worker active rahega:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Server ko band karne par worker gracefully stop hota hai. WhatsApp ya Ollama
temporary unavailable ho to worker error log karke retry karta hai.

Adapter official `GET /updates` long-poll call karta hai, `next_offset` save
karta hai, aur text messages ko official `POST /messages` par is payload ke
saath bhejta hai:

```json
{
  "messaging_product": "whatsapp",
  "to": "user:recipient-id",
  "type": "text",
  "text": {"body": "Roman Urdu jawab"}
}
```

Inbound text message mein `id`, `from`, `type: "text"` aur `text.body` hota
hai. `from` ki value ko reply ke `to` field mein unchanged bhejna hota hai.
API key ko kabhi source code, screenshots ya chat mein share na karein.

## Memory

Profile aur task data encrypted SQLite mein hota hai. `/memory/export` export
aur `/memory/forget/{category}` deletion ke liye hain. Production mein in
endpoints ke liye `APP_ADMIN_TOKEN` lazmi rakhein.

Operational endpoints ko admin token se protect kiya gaya hai:

```bash
curl -H "Authorization: Bearer $APP_ADMIN_TOKEN" http://localhost:8000/readyz
```

## Render/Railway deployment

Render Blueprint ya Railway repository deployment se one Docker service
chalayein aur `/app/data` ko persistent disk/volume par mount karein. Secrets
`MEMORY_KEY`, `APP_ADMIN_TOKEN`, `OLLAMA_API_KEY`, aur `WHATSAPP_API_KEY`
platform secret manager mein set karein. `MEMORY_PATH=/app/data/memory.db` aur
`WHATSAPP_ENABLED=true` rakhein.

Exactly one replica use karein: WhatsApp offset polling stateful hai aur
multiple replicas duplicate replies de sakti hain. Deploy ke baad `/healthz`,
authenticated `/readyz`, aur ek real WhatsApp message smoke-test karein.
Rollback previous platform revision par karein; logs mein secrets ya message
contents na likhein.
