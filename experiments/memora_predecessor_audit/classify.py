#!/usr/bin/env python3
"""Classify pinned public Memora lifecycle outcomes with an in-process API double.

This script performs no network calls and writes only an aggregate JSON receipt.
It does not write to either repository or publish conversation text.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

PINNED_DATASET = "a6493188efc836d6511ed5e4163fe3ba87da30ff"
PINNED_ADAPTER = "a99366cd21a29c2d7aabaf600884f07c9d8e4f5e"
PINNED_CORPUS_SHA256 = (
    "7835f7a353a0cbb81f9db2539c554e8fd852ffd0d31191cc9298fad2b93c4736"
)
PINNED_ADAPTER_SHA256 = (
    "40f264c1235b545bdd8d8e6cab14a612ea4c9fc7d87d8de7bf5ace73a8fae25a"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(path):
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def label(parts):
    return "|".join(str(part) for part in parts)


def classify_unresolved(operation, result, previous, prior_history, details):
    """Classify only missing-predecessor stores and skipped deletes."""
    unresolved = (
        operation == "update"
        and result["status"] == "stored"
        and not result.get("superseded")
    ) or (operation == "delete" and result["status"] == "skipped")
    if not unresolved:
        return None
    prior = previous[-1] if previous else None
    recorded = prior_history[-1] if prior_history else None
    group = (
        operation,
        prior["operation"] if prior else "none",
        prior["status"] if prior else "none",
        recorded.get("operation", "none") if recorded else "not_supplied",
    )
    mismatch = bool(
        recorded
        and prior
        and str(recorded.get("session_id")) != str(prior["session_id"])
    )
    shape = (
        None
        if recorded
        else (
            operation,
            details.get("operation_converted") or "native",
            details.get("pool_status") or "none",
        )
    )
    return label(group), label(shape) if shape else None, mismatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", required=True, type=Path, help="Pinned Memora repository"
    )
    parser.add_argument(
        "--adapter-worktree", required=True, type=Path, help="Pinned eval repository"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="New JSON receipt path"
    )
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    adapter = args.adapter_worktree.resolve()
    data_revision = git_head(dataset)
    adapter_revision = git_head(adapter)
    if data_revision != PINNED_DATASET or adapter_revision != PINNED_ADAPTER:
        raise RuntimeError("Dataset or adapter revision does not match pinned commits")
    if args.output.exists():
        raise RuntimeError("Refusing to overwrite an existing receipt")
    root = dataset / "data"
    all_files = sorted(root.glob("*/*/conversations/session_*.json"))
    corpus_digest = hashlib.sha256()
    for path in all_files:
        corpus_digest.update(str(path.relative_to(root)).encode("utf-8") + b"\x00")
        corpus_digest.update(bytes.fromhex(sha(path)))
    adapter_sha256 = sha(adapter / "scripts" / "benchmarks" / "memora_fama_adapter.py")
    if (
        corpus_digest.hexdigest() != PINNED_CORPUS_SHA256
        or adapter_sha256 != PINNED_ADAPTER_SHA256
    ):
        raise RuntimeError(
            "Dataset files or adapter source do not match pinned digests"
        )
    sys.path.insert(0, str(adapter / "scripts" / "benchmarks"))
    from memora_fama_adapter import (
        AutoMemFamaSystem,
        _ProtocolSmokeTransport,
        _safe_tag,
    )

    totals = Counter()
    by_period = defaultdict(Counter)
    missing_groups = Counter()
    no_history_shapes = Counter()
    mismatched_history = 0
    for period in ("weekly", "monthly", "quarterly"):
        for directory in sorted((root / period).glob("*/conversations")):
            system = AutoMemFamaSystem(
                directory.parent.name + "_" + period,
                request_json=_ProtocolSmokeTransport().request,
            )
            timeline = defaultdict(list)
            paths = sorted(
                directory.glob("session_*.json"),
                key=lambda p: int(p.stem.split("_")[1]),
            )
            for path in paths:
                data = json.loads(path.read_text(encoding="utf-8"))
                operation = str(data.get("operation") or "add").lower()
                details = data.get("operation_details") or {}
                key = system._fact_key(data)
                previous = list(timeline[key])
                old = details.get("old_item")
                prior_history = [
                    entry
                    for entry in (details.get("session_history") or [])
                    if isinstance(entry, dict)
                    and entry.get("session_id") != data.get("session_id")
                ]
                totals["sessions"] += 1
                totals["operation_" + operation] += 1
                by_period[period][operation] += 1
                if operation == "update":
                    totals["update_old_type_" + type(old).__name__] += 1
                    renamed = (
                        isinstance(old, str)
                        and bool(_safe_tag(old))
                        and bool(key)
                        and _safe_tag(old) != key
                    )
                    if renamed:
                        totals["renamed_updates"] += 1
                        by_period[period]["renamed_updates"] += 1
                        if system._current_by_fact.get(_safe_tag(old)):
                            totals["renamed_predecessor_present"] += 1
                        else:
                            totals["renamed_predecessor_missing"] += 1
                        if system._current_by_fact.get(key):
                            totals["renamed_destination_active"] += 1
                result = system.add_conversation_to_memory(data)
                if operation == "update":
                    totals["update_result_" + result["status"]] += 1
                    totals["updates_superseded"] += bool(result.get("superseded"))
                elif operation == "delete":
                    totals["delete_result_" + result["status"]] += 1
                classification = classify_unresolved(
                    operation, result, previous, prior_history, details
                )
                if classification:
                    group, shape, mismatch = classification
                    missing_groups[group] += 1
                    mismatched_history += mismatch
                    if shape:
                        no_history_shapes[shape] += 1
                timeline[key].append(
                    {
                        "session_id": data.get("session_id"),
                        "operation": operation,
                        "status": result["status"],
                    }
                )
    result = {
        "kind": "memora-adapter-predecessor-classification",
        "dataset_revision": data_revision,
        "adapter_revision": adapter_revision,
        "dataset_conversation_file_count": len(all_files),
        "dataset_conversation_tree_sha256": corpus_digest.hexdigest(),
        "adapter_source_sha256": adapter_sha256,
        "method": "Numeric session order, isolated in-process transport per period/persona; classify last operation for the adapter-normalized key and compare recorded session history when supplied.",
        "limitations": [
            "Protocol double, not AutoMem server, retrieval quality, FAMA scoring or proof of semantic identity.",
            "Normalized keys may collapse distinct strings; updates after deletes may be valid reintroductions.",
            "Whole-conversation capture may contain facts beyond the tracked item.",
            "Public dataset only; no provider calls or raw conversation content in this receipt.",
        ],
        "totals": dict(sorted(totals.items())),
        "by_period": {k: dict(sorted(v.items())) for k, v in sorted(by_period.items())},
        "unresolved_by_last_same_key_and_recorded_history": dict(
            sorted(missing_groups.items())
        ),
        "unresolved_without_history_by_operation_conversion_and_pool": dict(
            sorted(no_history_shapes.items())
        ),
        "recorded_history_last_session_mismatches": mismatched_history,
    }
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sessions": totals["sessions"],
                "dataset_sha256": corpus_digest.hexdigest(),
                "unresolved": sum(missing_groups.values()),
                "renamed": totals["renamed_updates"],
                "history_mismatches": mismatched_history,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
