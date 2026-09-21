# Personal WhatsApp AI Agent Design

## Scope

Build a local-first personal AI agent for Danyal Mudassar using LangChain and
LangGraph. The agent will use an Ollama Cloud model as its primary LLM and will
be prepared for WhatsApp's official custom third-party personal-agent API/key
flow. The first implementation targets a local Docker deployment and supports
personal assistant, research, and developer roles.

The WhatsApp integration must use the official API contract available to the
user's account. Unofficial WhatsApp Web automation is out of scope.

## Goals

- Provide a modular LangGraph supervisor that routes requests to focused role
  subgraphs.
- Use LangChain for typed, permission-gated tools.
- Keep the profile and long-term memory in encrypted local storage.
- Produce concise Roman Urdu responses, retaining English technical terms where
  useful.
- Support local CLI/API operation before WhatsApp credentials and API details
  are available.
- Make external side effects explicit and confirmation-gated.

## Non-goals

- Replacing Meta's native Business Agent.
- Storing or training on WhatsApp conversations without an explicit policy.
- Unofficial WhatsApp Web automation.
- Autonomous destructive shell, GitHub write, messaging, or account actions.
- Treating unverified credentials or certificate claims as independently
  verified facts.

## Architecture

### Components

1. **WhatsApp adapter**: Translates the official personal-agent API messages
   into an internal message contract and sends responses back. Meta-specific
   payload handling stays isolated here.
2. **Gateway/API**: Validates webhook requests, authenticates the integration,
   applies rate limits, assigns correlation IDs, and deduplicates events.
3. **LangGraph supervisor**: Maintains graph state, classifies intent, and
   routes to the Personal Assistant, Researcher, Developer, or Memory
   subgraphs.
4. **LangChain tool layer**: Exposes typed tools with allowlists, timeouts,
   audit metadata, and permission checks.
5. **Ollama Cloud adapter**: Provides the LangChain chat-model interface for the
   configured Ollama Cloud endpoint/model, with bounded retries and explicit
   failure states.
6. **Memory layer**: Stores encrypted profile data, approved preferences,
   conversation summaries, and task state in local files and SQLite.
7. **Response policy**: Applies Roman Urdu formatting, WhatsApp-friendly
   length, research citations, and confirmation requirements.

### Data flow

WhatsApp message -> gateway validation -> LangGraph state initialization ->
memory retrieval -> supervisor routing -> tool/subgraph execution -> response
policy -> WhatsApp response -> encrypted audit metadata.

The same graph must be callable through a local CLI/API fixture without
WhatsApp, so integration testing does not depend on the external service.

## Tools

The initial tool set is:

- **Profile**: Read approved profile fields from the encrypted vault. Contact
  fields are masked by default.
- **Notes/tasks**: Create, read, update, and complete local notes and tasks.
- **Research**: Search the web and return summaries with source URLs.
- **Developer**: Read and analyze permitted workspace files. Destructive or
  arbitrary shell execution is not allowed by default.
- **GitHub**: Read-only repository, issue, and pull-request access by default.
  Any write action requires explicit confirmation.
- **Calculator/date**: Deterministic local calculations and date utilities.

Every tool uses a typed input/output contract, bounded execution timeout,
structured error result, and audit event. Tool failures must be surfaced rather
than replaced with fabricated success.

## Memory and privacy

- **Thread state** contains the current conversation and relevant tool results.
- **Long-term memory** contains only stable facts, approved preferences, and
  task summaries that are allowed by policy.
- The supplied profile is stored as full local memory in encrypted storage.
- Email and phone number are never included in ordinary responses without
  explicit confirmation.
- The agent supports show, forget, and export memory operations.
- Raw WhatsApp messages are not persisted as long-term memory by default.
- Profile and conversation content is sent to Ollama only when needed as prompt
  context; it is not treated as permission for permanent provider storage.
- Secrets are provided through environment/configuration outside version
  control. No credentials are committed.

## Safety and reliability

- Prompt-injection filtering is applied before tool selection.
- Tools are restricted by role and permission policy.
- External side effects require confirmation.
- Requests and tool calls carry correlation IDs and structured audit events.
- API failures use bounded retries and clear user-facing errors.
- Duplicate webhook events are idempotently ignored.
- Ollama and WhatsApp outages produce an explicit unavailable response or
  configured fallback; the agent must not claim an action succeeded.
- Fitness, health, cybersecurity, and other high-impact guidance uses
  appropriate safety boundaries and does not present the agent as a licensed
  professional.

## Deployment

The first deployment is local Docker Compose with:

- API/webhook service
- LangGraph worker/runtime
- encrypted local data volume
- health and readiness endpoints

An `.env.example` will document required settings without real secrets. The
official WhatsApp adapter is feature-flagged so the local CLI/API remains
usable while the account-specific API contract is being confirmed.

## Testing and rollout

### Tests

- Unit tests for supervisor routing, Roman Urdu response policy, tool schemas,
  memory permissions, and encryption/decryption.
- Integration tests with mocked Ollama and WhatsApp APIs.
- Security tests for prompt injection, secret leakage, unauthorized profile
  access, and destructive tool calls.
- End-to-end Docker tests using webhook fixtures and duplicate-event cases.

### Phases

1. Local CLI and mocked WhatsApp adapter.
2. Official WhatsApp API adapter with the user's credentials and contract.
3. Tool and memory hardening, backups, and recovery verification.
4. Optional 24/7 VPS deployment after local acceptance.

## Acceptance criteria

- A local message can be routed through LangGraph and answered using the
  configured Ollama Cloud model.
- Personal assistant, research, and developer routes work independently.
- Roman Urdu is the default response language.
- Profile data is encrypted at rest and inaccessible without the configured
  key.
- Unauthorized tools and contact-data disclosure are blocked.
- Tool failures and provider outages are explicit and test-covered.
- WhatsApp integration is isolated behind an official-contract adapter and
  does not require unofficial automation.
