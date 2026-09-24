import argparse
import os
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="convaiinnovations/laya-multilingual")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()

    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    try:
        import laya
    except ImportError as exc:
        print(f"status=unavailable reason=missing_laya error={exc}")
        return 2

    started = time.perf_counter()
    try:
        agent = laya.load(args.model)
        result = agent.predict(
            {"body": "Mujhe invoice 4411 ke liye do baar charge kiya gaya hai."},
            {
                "department": {
                    "type": "choice",
                    "instructions": "Which team should handle this?",
                    "criteria": {"billing": "payments and refunds", "technical": "bugs"},
                },
                "urgency": {
                    "type": "score",
                    "instructions": "How urgent is this?",
                    "criteria": ["normal", "soon", "blocking"],
                },
            },
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"status=failed mode=local model={args.model} error={type(exc).__name__}:{exc}")
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"status=passed mode=local model={args.model} latency_ms={elapsed_ms:.2f}")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
