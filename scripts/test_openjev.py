import argparse
import asyncio
import os

import httpx

from app.decision_backends import OpenJevBackend
from app.decision_models import DecisionRequest


def request() -> DecisionRequest:
    return DecisionRequest(
        state={"body": "fix login"},
        questions={
            "route": {
                "type": "choice",
                "instructions": "Which workflow?",
                "criteria": {"developer": "code", "researcher": "sources"},
            }
        },
    )


async def run(url: str, mock: bool) -> int:
    if mock:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "answers": {"route": {"choice": "developer", "probability": 0.97}},
                    "confidence": 0.97,
                },
            )
        )
        mode = "mock"
    else:
        if not url:
            print("status=unavailable mode=live reason=OPENJEV_URL_not_configured")
            return 2
        transport = None
        mode = "live"

    try:
        result = await OpenJevBackend(url or "http://mock", 5, transport=transport).decide(request())
    except (httpx.HTTPError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"status=failed mode={mode} error={type(exc).__name__}:{exc}")
        return 1
    print(f"status=passed mode={mode} backend={result.backend} confidence={result.confidence}")
    print(result.model_dump(mode="json"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--url", default=os.getenv("OPENJEV_URL", ""))
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.mock))


if __name__ == "__main__":
    raise SystemExit(main())
