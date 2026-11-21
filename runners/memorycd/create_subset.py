#!/usr/bin/env python3
"""Create a deterministic, small MemoryCD subset from the released JSONL.gz."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--users", type=int, default=4)
    parser.add_argument("--target-domain", default="Books")
    parser.add_argument("--source-domain", default="Electronics")
    parser.add_argument("--num-test", type=int, default=1)
    parser.add_argument("--max-memory-per-domain", type=int, default=8,
                        help="Keep this many pre-test target/source interactions per domain.")
    args = parser.parse_args()

    selected = []
    with gzip.open(args.input, "rt", encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            interactions = record.get("interactions") or {}
            target_count = len(interactions.get(args.target_domain) or [])
            source_count = len(interactions.get(args.source_domain) or [])
            if target_count >= args.num_test + 1 and source_count >= 1:
                target = sorted(interactions[args.target_domain], key=lambda item: item.get("timestamp", 0))
                source_items = sorted(interactions[args.source_domain], key=lambda item: item.get("timestamp", 0))
                # Preserve the test tail and a bounded, chronologically ordered history.
                trimmed = dict(record)
                trimmed["interactions"] = {
                    args.target_domain: target[-(args.max_memory_per_domain + args.num_test):],
                    args.source_domain: source_items[-args.max_memory_per_domain:],
                }
                selected.append(trimmed)
            if len(selected) == args.users:
                break
    if len(selected) != args.users:
        raise SystemExit(f"Found only {len(selected)} eligible users; expected {args.users}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as destination:
        for record in selected:
            destination.write(json.dumps(record, ensure_ascii=False) + "\n")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "source": str(args.input),
                "users": [record["user_id"] for record in selected],
                "target_domain": args.target_domain,
                "source_domain": args.source_domain,
                "num_test": args.num_test,
                "max_memory_per_domain": args.max_memory_per_domain,
                "eligibility": f"{args.target_domain} >= {args.num_test + 1}; {args.source_domain} >= 1",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(selected)} users to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
