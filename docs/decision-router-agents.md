# Decision Router for Coding Agents

The decision router gives coding agents typed decisions without exposing model
credentials. GitHub Copilot CLI, Antigravity, and other agents can use either
the authenticated HTTP endpoint or the optional MCP server.

## HTTP

```bash
curl -X POST "$DECISION_URL/decide" \
  -H "Authorization: Bearer $DECISION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"state":{"body":"fix login"},"questions":{"risk":{"type":"noul","instructions":"Is this high risk?"}}}'
```

The response includes `answers`, `confidence`, `backend`, `latency_ms`,
`review_required`, and `reason_code`. Agents must stop for human approval when
`review_required` is true.

## Python

```python
import httpx

payload = {
    "state": {"body": "fix login"},
    "questions": {
        "route": {
            "type": "choice",
            "instructions": "Choose the workflow.",
            "criteria": {"developer": "code", "researcher": "sources"},
        }
    },
}
response = httpx.post(
    f"{decision_url}/decide",
    headers={"Authorization": f"Bearer {decision_token}"},
    json=payload,
    timeout=5,
)
decision = response.json()
if decision["review_required"]:
    raise RuntimeError("Human review required")
```

## MCP

Install the optional extra and expose the server through your local MCP
launcher:

```bash
.venv/bin/pip install -e '.[decision-mcp]'
```

The server exposes `decide`, `route`, `risk_check`, and `review_required`.
Configure Copilot CLI, Antigravity, or another MCP-capable agent to launch the
server locally and pass the decision service configuration through environment
variables. Keep `JEV_API_KEY`, `WHATSAPP_API_KEY`, and all other secrets out of
agent tool arguments and prompts.

Antigravity installations without MCP support can call the same HTTP endpoint.
The model backend is intentionally hidden behind the stable contract, so
agents do not need separate integrations for Laya, OpenJev, or Jev.
