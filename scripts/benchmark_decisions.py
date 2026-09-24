import argparse
import asyncio
import os
import statistics
import time

import httpx

from app.decision_backends import OpenJevBackend
from app.decision_models import DecisionRequest


def request() -> DecisionRequest:
    return DecisionRequest(
        state={"body": "charged twice"},
        questions={
            "department": {
                "type": "choice",
                "instructions": "Which team should handle this?",
                "criteria": {"billing": "payments", "technical": "bugs"},
            }
        },
    )


async def main_async(backend_name: str, iterations: int, mock: bool) -> int:
    if backend_name == "openjev":
        url = os.getenv("OPENJEV_URL", "")
        if mock:
            transport = httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "answers": {"department": {"choice": "billing", "probability": 0.9}},
                        "confidence": 0.9,
                    },
                )
            )
            url = "http://mock"
            mode = "mock"
        elif not url:
            print("status=skipped backend=openjev reason=OPENJEV_URL_not_configured")
            return 2
        else:
            transport = None
            mode = "live"
        backend = OpenJevBackend(url, 5, transport=transport)
    else:
        print(f"status=skipped backend={backend_name} reason=unsupported_benchmark_backend")
        return 2

    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        try:
            await backend.decide(request())
        except (httpx.HTTPError, OSError, RuntimeError, TypeError, ValueError) as exc:
            print(f"status=failed mode={mode} backend={backend_name} error={type(exc).__name__}:{exc}")
            return 1
        samples.append((time.perf_counter() - started) * 1000)

    print(
        f"status=passed mode={mode} backend={backend_name} iterations={iterations} "
        f"median_ms={statistics.median(samples):.2f} p95_ms={statistics.quantiles(samples, n=20)[18]:.2f}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="openjev")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    return asyncio.run(main_async(args.backend, args.iterations, args.mock))


if __name__ == "__main__":
    raise SystemExit(main())
