# System One Decision Router Validation

Date: 2026-09-24

## Environment

- Project: `personal-whatsapp-ai-agent`
- Python: 3.12 virtual environment in the isolated feature worktree
- Host profile supplied for this task: Intel Core i5-6300U, 12 GiB RAM, CPU-only
- Decision-router branch: `feature/system-one-decision-router`

## Automated validation

| Check | Result |
|---|---|
| `.venv/bin/pytest -q` | **70 passed** |
| `.venv/bin/ruff check app tests scripts` | **passed** |
| `.venv/bin/python scripts/test_openjev.py --mock` | **passed**, mode `mock` |
| `.venv/bin/python scripts/benchmark_decisions.py --iterations 10 --mock` | **passed**, median `0.43 ms`, p95 `1.43 ms` |
| `git diff --check` | **passed** |
| `typesafe-sdk` import | **passed**, version `0.7.1` |

The mock benchmark measures adapter/serialization overhead only. It is not a
model-inference benchmark.

## Backend status

### Laya

Status: **blocked before model load**.

The optional `laya` package requires PyTorch. A normal install attempted to
pull a large CUDA-enabled PyTorch distribution, which is unsuitable for this
CPU-only host. A CPU-only PyTorch wheel was then attempted, but the 196.3 MB
download timed out at approximately 129 MB. Therefore no Laya checkpoint was
loaded and no local inference result is claimed.

The repository now documents the safer CPU path:

```bash
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.0'
.venv/bin/pip install -e '.[decision-local]' --no-deps
.venv/bin/pip install 'transformers>=4.48' 'safetensors>=0.4' 'huggingface-hub>=0.20' 'numpy>=1.20'
```

### OpenJev

Status: **adapter and mock contract passed; live access requires credentials**.

The adapter was aligned with OpenJev's documented `POST /v1/systemone` wire
contract and `openjev-latest` model name. The mock smoke test and benchmark
passed. A live probe against `https://api.codiv.ai` returned an authentication
failure, as expected without an API key.

### Jev

Status: **remote contract path available; live test skipped**.

Jev is treated as a remote, closed-source backend. The compatible
`typesafe-sdk` package installed and imported successfully. No live Jev
request was made because `JEV_URL` and `JEV_API_KEY` were not configured.
The implementation does not claim local Jev weights.

## Compatibility

| Client | Interface | Status |
|---|---|---|
| GitHub Copilot CLI / coding agents | Authenticated HTTP or MCP | Contract implemented and documented |
| Antigravity | MCP where supported, otherwise HTTP | Contract implemented and documented |
| Other coding agents | OpenAPI-shaped HTTP JSON contract | Contract implemented and documented |

All clients receive typed answers, confidence, backend, latency, reason code,
and `review_required`; they do not receive provider credentials.
