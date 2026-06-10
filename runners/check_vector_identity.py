#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from apply_metadata_treatment import qdrant_vector_hashes


def is_local_qdrant_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def compare_vector_hashes(
    baseline_hashes: dict[str, str],
    candidate_hashes: dict[str, str],
    *,
    variant: str,
) -> dict[str, Any]:
    baseline_ids = set(baseline_hashes)
    candidate_ids = set(candidate_hashes)
    common_ids = baseline_ids & candidate_ids
    changed_ids = sorted(
        memory_id
        for memory_id in common_ids
        if baseline_hashes[memory_id] != candidate_hashes[memory_id]
    )
    missing_ids = sorted(baseline_ids - candidate_ids)
    extra_ids = sorted(candidate_ids - baseline_ids)
    vectors_identical = not changed_ids and not missing_ids and not extra_ids
    return {
        "variant": variant,
        "baseline_vector_count": len(baseline_hashes),
        "candidate_vector_count": len(candidate_hashes),
        "common_vector_count": len(common_ids),
        "changed_vector_count": len(changed_ids),
        "changed_vector_ids_sample": changed_ids[:20],
        "missing_candidate_count": len(missing_ids),
        "missing_candidate_ids_sample": missing_ids[:20],
        "extra_candidate_count": len(extra_ids),
        "extra_candidate_ids_sample": extra_ids[:20],
        "vectors_identical": vectors_identical,
    }


def write_identity_artifacts(
    vector_identity: dict[str, Any],
    *,
    plan_output: Path,
    summary_output: Path,
    vector_preflight_output: Path,
) -> None:
    plan_output.parent.mkdir(parents=True, exist_ok=True)
    plan_output.write_text("")

    preflight = {
        "variant": vector_identity["variant"],
        "vectors_identical": bool(vector_identity["vectors_identical"]),
        "vector_identity": vector_identity,
        "changed_vector_count": vector_identity["changed_vector_count"],
        "missing_candidate_count": vector_identity["missing_candidate_count"],
        "extra_candidate_count": vector_identity["extra_candidate_count"],
    }
    vector_preflight_output.parent.mkdir(parents=True, exist_ok=True)
    vector_preflight_output.write_text(json.dumps(preflight, indent=2) + "\n")

    summary = {
        "variant": vector_identity["variant"],
        "tag_plan_count": 0,
        "embedding_plan_count": 0,
        "graph_updates": 0,
        "qdrant_updates": 0,
        "vector_updates": 0,
        "vector_identity": vector_identity,
        "vector_preflight": preflight,
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2) + "\n")


def _connect_qdrant(url: str, api_key: str | None) -> Any:
    from qdrant_client import QdrantClient  # type: ignore

    return QdrantClient(url=url, api_key=api_key or None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline/candidate Qdrant vectors")
    parser.add_argument("--variant", default="server-metadata-search")
    parser.add_argument("--baseline-qdrant-url", required=True)
    parser.add_argument("--candidate-qdrant-url", required=True)
    parser.add_argument("--baseline-qdrant-api-key", default="")
    parser.add_argument("--candidate-qdrant-api-key", default="")
    parser.add_argument("--collection", default="memories")
    parser.add_argument("--plan-output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--vector-preflight-output", required=True, type=Path)
    args = parser.parse_args()

    for label, url in {
        "baseline": args.baseline_qdrant_url,
        "candidate": args.candidate_qdrant_url,
    }.items():
        if not is_local_qdrant_url(url):
            raise SystemExit(f"refusing non-local {label} Qdrant URL: {url}")

    baseline = _connect_qdrant(args.baseline_qdrant_url, args.baseline_qdrant_api_key)
    candidate = _connect_qdrant(args.candidate_qdrant_url, args.candidate_qdrant_api_key)
    vector_identity = compare_vector_hashes(
        qdrant_vector_hashes(baseline, args.collection),
        qdrant_vector_hashes(candidate, args.collection),
        variant=args.variant,
    )
    write_identity_artifacts(
        vector_identity,
        plan_output=args.plan_output,
        summary_output=args.summary_output,
        vector_preflight_output=args.vector_preflight_output,
    )
    print(json.dumps(vector_identity, indent=2))
    return 0 if vector_identity["vectors_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
