#!/usr/bin/env python3
"""Report the safe, offline DolphinBench protocol-smoke boundary.

This intentionally does not invoke the upstream ingest/evaluate commands.
Those commands require paid agent and Azure judge calls and an all-persona,
all-task submission record.  The script makes that boundary machine-readable
so no caller can confuse adapter tests with a benchmark result.
"""

from __future__ import annotations

import json


def main() -> int:
    print(json.dumps({
        "benchmark": "DolphinBench",
        "status": "not_scored",
        "smoke_scope": "AutoMem HTTP protocol double only",
        "accuracy": None,
        "total_cost_usd": None,
        "median_task_latency_s": None,
        "reason": (
            "Upstream non-offline ingestion and evaluation require --confirm-paid-calls; "
            "semantic grading requires Azure gpt-5.6-sol credentials. No paid run was executed."
        ),
        "next_steps": [
            "Implement the participant agent loop around AutoMemDolphinBenchBackend.",
            "Run one persona with paid agent and judge credentials.",
            "Report measured accuracy, total cost, and median task latency from saved evidence.",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
