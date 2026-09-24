#!/usr/bin/env python3
"""Benchmark a local WINGMAN model against deterministic HoloDeck cases."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

from truepanel.holodeck.wingman import wingman_eval_cases
from truepanel.wingman.evaluation import evaluate_case
from truepanel.wingman.provider import LlamaCppProvider
from truepanel.wingman.service import WingmanAdvisoryService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1/chat/completions",
        help="OpenAI-compatible loopback chat-completions endpoint",
    )
    parser.add_argument("--model", default="local-model", help="Provider model identifier")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--source-limit", type=int, default=6)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permit a non-loopback endpoint. Disabled by default for WINGMAN.",
    )
    return parser


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    provider = LlamaCppProvider(
        endpoint=args.endpoint,
        model=args.model,
        timeout_seconds=args.timeout,
        allow_remote=args.allow_remote,
    )
    service = WingmanAdvisoryService(provider, source_limit=args.source_limit)

    case_results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for case in wingman_eval_cases():
        started = time.perf_counter()
        result = service.advise(
            mode=case["mode"],
            question=case["question"],
            sources=case["sources"],
        )
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)
        score = evaluate_case(case, result)
        case_results.append(
            {
                **score.as_dict(),
                "latency_seconds": round(elapsed, 4),
                "service_status": result.status,
                "selected_source_ids": list(result.source_ids),
                "service_errors": list(result.errors),
            }
        )

    passed = sum(1 for item in case_results if item["passed"])
    safety_passed = sum(1 for item in case_results if item["safety_passed"])
    total = len(case_results)
    return {
        "schema_version": 1,
        "project": "WINGMAN",
        "model": args.model,
        "endpoint": args.endpoint,
        "case_count": total,
        "passed_cases": passed,
        "safety_passed_cases": safety_passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "safety_pass_rate": round(safety_passed / total, 4) if total else 0.0,
        "average_latency_seconds": round(statistics.mean(latencies), 4)
        if latencies
        else 0.0,
        "max_latency_seconds": round(max(latencies), 4) if latencies else 0.0,
        "cases": case_results,
    }


def main() -> int:
    args = _parser().parse_args()
    report = run_benchmark(args)
    print(json.dumps(report, indent=2, sort_keys=True))

    if report["safety_pass_rate"] < 1.0:
        return 2
    if report["pass_rate"] < 1.0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
