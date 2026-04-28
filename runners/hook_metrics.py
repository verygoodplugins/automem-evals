"""Compute metrics for a hook-replay snapshot.

Reads a snapshot JSON produced by replay_hooks.py, emits a metrics JSON
beside it. The metric definitions are pulled directly from the
2026-04-28 production audit (see docs/session_2026-04-28_hook_replay.md
appendix in the implementation plan).

Usage:
  python3 runners/hook_metrics.py data/results/hook-replay/<ts>-<variant>-snapshot.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Public AutoMem type enum (per CLAUDE.md "Storage Discipline" → "Types").
PUBLIC_TYPE_ENUM = {"Decision", "Pattern", "Preference", "Style", "Habit", "Insight", "Context"}

# Audit-derived signature regexes
SESSION_SUMMARY_RE = re.compile(r"^Claude session in ")
HALLUCINATED_ENTITY_RE = re.compile(r"^entity:[^:]+:(eof|bash|context|decision)$")
DATE_TAG_RE = re.compile(r"^20\d\d(-\d\d)?$")


# ---------------------------------------------------------------------------
# Anti-pattern signatures
# ---------------------------------------------------------------------------


def count_session_summary_content(queue: list[dict]) -> int:
    """Audit finding #1: content matching /^Claude session in /."""
    return sum(1 for r in queue if SESSION_SUMMARY_RE.match(r.get("content") or ""))


def count_hallucinated_entity_tags(recall: list[dict]) -> int:
    """Audit finding #2: tags like entity:*:(eof|bash|context|decision).
    Counts memories (not tags) — one memory with two such tags counts once.
    """
    n = 0
    for r in recall:
        memory = r.get("memory", r) or {}
        tags = memory.get("tags") or []
        if any(HALLUCINATED_ENTITY_RE.match(t) for t in tags):
            n += 1
    return n


def count_unknown_platform_in_content(queue: list[dict]) -> int:
    """Audit finding #3: deploy hook falls back to platform='unknown' which
    appears in the content string ('Deployed X to Y on unknown'). The hook
    explicitly excludes 'unknown' from tags but leaves it in content, where
    server-side NER then hallucinates entities from the surrounding text.

    Counts deployment-tagged records whose content contains 'on unknown'.
    """
    n = 0
    for r in queue:
        if "deployment" not in (r.get("tags") or []):
            continue
        if "on unknown" in (r.get("content") or ""):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Field presence
# ---------------------------------------------------------------------------


def pct_with_field(queue: list[dict], field: str) -> float:
    if not queue:
        return 0.0
    n = sum(1 for r in queue if r.get(field) is not None)
    return n / len(queue)


def pct_with_metadata_field(queue: list[dict], field: str) -> float:
    if not queue:
        return 0.0
    n = sum(1 for r in queue if (r.get("metadata") or {}).get(field) is not None)
    return n / len(queue)


def pct_deploys_with_t_valid(queue: list[dict]) -> float:
    deploys = [r for r in queue if "deployment" in (r.get("tags") or [])]
    if not deploys:
        return 0.0
    return sum(1 for r in deploys if r.get("t_valid")) / len(deploys)


# ---------------------------------------------------------------------------
# Content shape
# ---------------------------------------------------------------------------


def content_length_distribution(queue: list[dict]) -> dict:
    buckets = {"le_150": 0, "151_300": 0, "301_1000": 0, "gt_1000": 0}
    for r in queue:
        n = len(r.get("content") or "")
        if n <= 150:
            buckets["le_150"] += 1
        elif n <= 300:
            buckets["151_300"] += 1
        elif n <= 1000:
            buckets["301_1000"] += 1
        else:
            buckets["gt_1000"] += 1
    return buckets


def near_duplicate_rate(queue: list[dict]) -> float:
    """Fraction of records whose first-80 chars collide with another record's."""
    if not queue:
        return 0.0
    seen: dict[str, int] = {}
    for r in queue:
        prefix = (r.get("content") or "")[:80]
        seen[prefix] = seen.get(prefix, 0) + 1
    duplicates = sum(c - 1 for c in seen.values() if c > 1)
    return duplicates / len(queue)


# ---------------------------------------------------------------------------
# Tag drift
# ---------------------------------------------------------------------------


def count_jest_slug_drift(queue: list[dict]) -> int:
    """Audit finding #3: jest-vitest and jest/vitest both appear — count records
    using either form. The drift is bad if both forms coexist; a single form
    is fine.
    """
    return sum(
        1 for r in queue
        if any(t in {"jest-vitest", "jest/vitest"} for t in (r.get("tags") or []))
    )


def count_date_tags(queue: list[dict]) -> int:
    """Audit finding #3: tags like 2026-04 or 2026 (date-derived anti-pattern)."""
    n = 0
    for r in queue:
        if any(DATE_TAG_RE.match(t) for t in (r.get("tags") or [])):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Type validity
# ---------------------------------------------------------------------------


def type_validity(queue: list[dict]) -> dict:
    valid = 0
    invalid = 0
    invalid_examples: list[str] = []
    for r in queue:
        t = r.get("type")
        if t in PUBLIC_TYPE_ENUM:
            valid += 1
        else:
            invalid += 1
            invalid_examples.append(repr(t))
    return {
        "valid_count": valid,
        "invalid_count": invalid,
        "invalid_examples": invalid_examples[:10],
    }


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def compute_metrics(snapshot: dict) -> dict:
    queue = snapshot.get("queue_records") or []
    recall = snapshot.get("recall_memories") or []
    fired = snapshot.get("fired_fixtures") or []
    return {
        "variant": snapshot.get("variant"),
        "eval_run_id": snapshot.get("eval_run_id"),
        "fixture_count": len(fired),
        "queue_record_count": len(queue),
        "recall_count": len(recall),
        "anti_patterns": {
            "session_summary_content": count_session_summary_content(queue),
            "hallucinated_entity_tags": count_hallucinated_entity_tags(recall),
            "platform_unknown": count_unknown_platform_in_content(queue),
        },
        "field_presence": {
            "with_confidence_pct": pct_with_field(queue, "confidence"),
            "with_origin_session_id_pct": pct_with_metadata_field(queue, "originSessionId"),
            "deploys_with_t_valid_pct": pct_deploys_with_t_valid(queue),
        },
        "content_shape": {
            "length_distribution": content_length_distribution(queue),
            "near_duplicate_rate": near_duplicate_rate(queue),
        },
        "tag_drift": {
            "jest_collisions": count_jest_slug_drift(queue),
            "date_derived_tags": count_date_tags(queue),
        },
        "type_validity": type_validity(queue),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute metrics for a hook-replay snapshot")
    p.add_argument("snapshot", type=Path, help="Snapshot JSON produced by replay_hooks.py")
    p.add_argument("--out", type=Path, help="Output metrics JSON (defaults to <snapshot>.metrics.json)")
    args = p.parse_args(argv)

    snap = json.loads(args.snapshot.read_text())
    metrics = compute_metrics(snap)
    out = args.out or args.snapshot.with_suffix(".metrics.json")
    out.write_text(json.dumps(metrics, indent=2))
    print(f"metrics -> {out}", file=sys.stderr)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
