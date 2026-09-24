# System One Decision Router Integration

## Goal

Add a safe, provider-independent decision layer for the existing WhatsApp
LangGraph agent. The decision layer will use local Laya/OpenJev backends when
available and an optional remote Jev adapter when the user has valid access.
It will make typed decisions for routing and risk control, while Ollama remains
responsible for conversational Roman Urdu responses.

## Scope

### Included

- Install and smoke-test Laya in an isolated Python environment.
- Install and smoke-test OpenJev in a separate isolated environment.
- Add a Jev API/SDK contract adapter without pretending that closed-source Jev
  weights can be installed locally.
- Define one internal decision contract:
  - input state and typed questions
  - answers
  - probabilities/confidence
  - selected backend
  - latency
  - fallback or unavailable reason
- Add a sidecar-style HTTP decision router with backend fallback.
- Integrate decisions into the existing LangGraph flow for intent, urgency,
  escalation, tool selection, and language hints.
- Expose the same contract through MCP and documented HTTP/OpenAPI usage for
  GitHub Copilot CLI, Antigravity, and other coding agents.
- Add deterministic fixtures, contract tests, timeout/fallback tests, latency
  measurements, malformed-input tests, and secret-redaction tests.
- Document installation, local operation, agent integration, and limitations.

### Excluded

- Replacing Ollama as the conversational response generator.
- Treating a decision model as a general-purpose chat or reasoning model.
- Claiming Jev local installation or local weights when only an API is
  available.
- Automatic production changes, device reboots, or high-risk tool execution
  without existing approval controls.

## Architecture

The existing FastAPI/LangGraph application remains the orchestration layer.
The decision router is a bounded internal service/interface with a stable
request and response schema. Laya multilingual is the preferred local backend.
OpenJev is the local fallback. Jev is an optional remote backend. If all
decision backends fail, the existing LangGraph path continues with an explicit
decision-unavailable state rather than silently fabricating confidence.

The decision model never generates user-facing prose. LangGraph continues to
assemble tools, memory, provider calls, and natural Roman Urdu output.

## Decision Contract

`POST /decide` accepts a JSON object containing a state payload and typed
questions. The response contains:

- `answers`: typed answer values and probabilities
- `confidence`: aggregate or per-answer confidence where supported
- `backend`: `laya`, `openjev`, or `jev`
- `latency_ms`
- `review_required`
- `reason_code`

The contract must reject malformed questions and must distinguish timeout,
backend-unavailable, authentication failure, and low-confidence results.

## WhatsApp and LangGraph Flow

1. Receive and normalize an inbound WhatsApp message.
2. Ask the decision router for intent, urgency, escalation, tool-selection, and
   language hints.
3. Apply confidence thresholds and mark risky or ambiguous cases for review.
4. Continue through existing LangGraph tools, memory, and provider fallback.
5. Generate the final natural Roman Urdu response with Ollama or another chat
   provider.
6. Record backend, latency, confidence, and safe reason codes without logging
   secrets or full private message content.

## Coding-Agent Compatibility

The router will expose the same contract in two forms:

- MCP tools such as `decide`, `route`, `risk_check`, and `review_required`.
- Authenticated HTTP/OpenAPI endpoints with curl, Python, and generic JSON
  examples.

GitHub Copilot CLI, Antigravity, and other coding agents can call the router
without knowing which model is active. High-risk operations must use the
returned `review_required` signal and existing human-approval controls.

## Installation and Testing

Stage 1 uses isolated environments and never modifies the production runtime
until smoke tests pass:

1. Install Laya and load the multilingual checkpoint.
2. Run typed routing, urgency, multilingual, and CPU latency fixtures.
3. Install OpenJev according to its documented repository instructions and run
   the same contract fixtures.
4. Run Jev adapter contract tests; run a live authenticated smoke test only
   when credentials are explicitly configured.
5. Run router contract, fallback, timeout, malformed-input, redaction, and
   existing full-suite tests.

Benchmark output must label whether a result is local, mocked, or live and must
not report unavailable Jev access as a passing live test.

## Failure Handling and Security

- Use bounded timeouts and a circuit breaker per backend.
- Fail closed for high-risk decisions and require review when confidence is
  below the configured threshold.
- Return explicit unavailable/error states instead of success-shaped defaults.
- Keep model credentials in environment variables or the existing encrypted
  provider store.
- Redact credentials, tokens, and private message content from logs.
- Keep Laya/OpenJev dependencies isolated where their transitive dependencies
  could conflict with the existing application.

## Success Criteria

- Laya local install and representative typed decisions work on the available
  CPU-only machine, with measured latency and memory observations.
- OpenJev either passes the same contract or is reported with a precise,
  reproducible blocker.
- Jev adapter clearly distinguishes contract/mock/live status.
- Existing WhatsApp chat behavior remains conversational and Roman Urdu.
- Coding agents can call the documented MCP or HTTP interface.
- Existing tests and all new targeted tests pass.
