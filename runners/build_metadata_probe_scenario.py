#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from metadata_eval_common import (
    extract_metadata_signals,
    humanize_field,
    metadata_value_is_hidden,
    normalize_search_text,
    read_snapshot_memories,
)

HERE = Path(__file__).resolve().parent.parent


def load_snapshot_memories(snapshot: Path) -> list[dict[str, Any]]:
    return read_snapshot_memories(snapshot)


def _scenario_id(field: str, slug: str) -> str:
    base = f"MD-{field}-{slug}".upper()
    return "".join(ch if ch.isalnum() else "-" for ch in base).strip("-")[:96]


def _unique_scenario_id(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base

    suffix_number = 2
    while True:
        suffix = f"-{suffix_number}"
        candidate = f"{base[: 96 - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        suffix_number += 1


def _query_for(field: str, value: str) -> str:
    return f"memories with {humanize_field(field)} {normalize_search_text(value)}"


def build_probe_rows(
    memories: list[dict[str, Any]],
    *,
    max_scenarios: int = 200,
    limit: int = 10,
    include_people: bool = False,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for memory in memories:
        memory_id = str(memory.get("id") or "").strip()
        if not memory_id:
            continue
        content = str(memory.get("content") or "")
        tags = list(memory.get("tags") or [])
        for signal in extract_metadata_signals(memory, max_tags=50, include_people=include_people):
            if not metadata_value_is_hidden(signal.value, content, tags):
                continue
            grouped[(signal.field, signal.value, signal.slug)].add(memory_id)

    rows: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for (field, value, slug), ids in sorted(grouped.items(), key=lambda item: item[0]):
        expected_ids = sorted(ids)
        base_id = _scenario_id(field, slug)
        rows.append(
            {
                "id": _unique_scenario_id(base_id, used_ids),
                "expected_ids": expected_ids,
                "expected_field": field,
                "expected_value": value,
                "query": _query_for(field, value),
                "params": {"limit": limit},
            }
        )
        if len(rows) >= max_scenarios:
            break
    return rows


def _warmup_query_from_content(content: str) -> str | None:
    words = [word for word in normalize_search_text(content).split() if len(word) > 2]
    if len(words) < 3:
        return None
    return " ".join(words[:8])


def build_warmup_queries(
    memories: list[dict[str, Any]],
    *,
    max_queries: int = 5,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if max_queries <= 0:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for memory in memories:
        memory_id = str(memory.get("id") or "").strip()
        if not memory_id:
            continue
        query = _warmup_query_from_content(str(memory.get("content") or ""))
        if not query or query in seen:
            continue
        seen.add(query)
        rows.append(
            {
                "id": f"WARMUP-{len(rows) + 1:03d}",
                "expected_ids": [memory_id],
                "query": query,
                "params": {"limit": limit},
            }
        )
        if len(rows) >= max_queries:
            break
    return rows


def build_scenario(
    memories: list[dict[str, Any]],
    *,
    max_scenarios: int = 200,
    limit: int = 10,
    include_people: bool = False,
    warmup_count: int = 5,
) -> dict[str, Any]:
    return {
        "version": 1,
        "description": (
            "Self-supervised metadata probes generated from restore-compatible "
            "AutoMem snapshots. Expected IDs are memories whose target metadata "
            "value is absent from content and existing tags."
        ),
        "warmup_queries": build_warmup_queries(memories, max_queries=warmup_count),
        "scenarios": build_probe_rows(
            memories,
            max_scenarios=max_scenarios,
            limit=limit,
            include_people=include_people,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build metadata-only probe scenarios")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-scenarios", type=int, default=200)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--warmup-count", type=int, default=5)
    parser.add_argument("--include-people", action="store_true")
    args = parser.parse_args()

    memories = load_snapshot_memories(args.snapshot)
    scenario = build_scenario(
        memories,
        max_scenarios=max(1, args.max_scenarios),
        limit=max(1, args.limit),
        include_people=args.include_people,
        warmup_count=max(0, args.warmup_count),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scenario, indent=2) + "\n")
    print(f"wrote {len(scenario['scenarios'])} metadata probes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
