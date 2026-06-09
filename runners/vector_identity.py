#!/usr/bin/env python3
"""Compare Qdrant point ids and vectors between two local AutoMem stacks."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _vector_fingerprint(vector: Any) -> str:
    return json.dumps(vector, sort_keys=True, separators=(",", ":"))


def compare_vector_maps(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    sample_limit: int = 20,
) -> dict[str, Any]:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)
    missing_in_candidate = sorted(baseline_ids - candidate_ids)
    missing_in_baseline = sorted(candidate_ids - baseline_ids)
    shared = sorted(baseline_ids & candidate_ids)
    changed = [
        point_id
        for point_id in shared
        if _vector_fingerprint(baseline[point_id]) != _vector_fingerprint(candidate[point_id])
    ]
    return {
        "ok": not missing_in_candidate and not missing_in_baseline and not changed,
        "baseline_points": len(baseline),
        "candidate_points": len(candidate),
        "missing_in_candidate": len(missing_in_candidate),
        "missing_in_baseline": len(missing_in_baseline),
        "changed_vectors": len(changed),
        "missing_in_candidate_sample": missing_in_candidate[:sample_limit],
        "missing_in_baseline_sample": missing_in_baseline[:sample_limit],
        "changed_vectors_sample": changed[:sample_limit],
    }


def _request_json(
    url: str,
    body: dict[str, Any],
    api_key: str | None = None,
    *,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read())


def _request_json_with_retries(
    url: str,
    body: dict[str, Any],
    api_key: str | None,
    *,
    timeout_seconds: float,
    retries: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    attempts = max(0, retries) + 1
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            return _request_json(url, body, api_key, timeout_seconds=timeout_seconds)
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)
    assert last_error is not None
    raise last_error


def fetch_qdrant_vectors(
    qdrant_url: str,
    collection: str,
    *,
    api_key: str | None = None,
    batch_size: int = 256,
    limit: int = 0,
    request_timeout_seconds: float = 60,
    retries: int = 2,
    retry_delay_seconds: float = 1,
) -> dict[str, Any]:
    endpoint = (
        f"{qdrant_url.rstrip('/')}/collections/"
        f"{urllib.parse.quote(collection)}/points/scroll"
    )
    offset = None
    vectors: dict[str, Any] = {}
    while True:
        body: dict[str, Any] = {
            "limit": batch_size,
            "with_payload": False,
            "with_vector": True,
        }
        if offset is not None:
            body["offset"] = offset
        payload = _request_json_with_retries(
            endpoint,
            body,
            api_key,
            timeout_seconds=request_timeout_seconds,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        result = payload.get("result") or {}
        points = result.get("points") or []
        for point in points:
            point_id = str(point.get("id"))
            vectors[point_id] = point.get("vector")
            if limit and len(vectors) >= limit:
                return vectors
        offset = result.get("next_page_offset")
        if not offset or not points:
            return vectors


def write_failure_summary(path: pathlib.Path | str | None, exc: BaseException) -> dict[str, Any]:
    summary = {
        "ok": False,
        "error": str(exc) or exc.__class__.__name__,
        "error_type": exc.__class__.__name__,
    }
    if path:
        out = pathlib.Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-qdrant-url", required=True)
    parser.add_argument("--candidate-qdrant-url", required=True)
    parser.add_argument("--collection", default="memories")
    parser.add_argument("--baseline-api-key", default=None)
    parser.add_argument("--candidate-api-key", default=None)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=1)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    try:
        baseline = fetch_qdrant_vectors(
            args.baseline_qdrant_url,
            args.collection,
            api_key=args.baseline_api_key,
            batch_size=args.batch_size,
            limit=args.limit,
            request_timeout_seconds=args.timeout_seconds,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay_seconds,
        )
        candidate = fetch_qdrant_vectors(
            args.candidate_qdrant_url,
            args.collection,
            api_key=args.candidate_api_key,
            batch_size=args.batch_size,
            limit=args.limit,
            request_timeout_seconds=args.timeout_seconds,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay_seconds,
        )
    except Exception as exc:
        summary = write_failure_summary(args.out, exc)
        print(json.dumps(summary, sort_keys=True))
        return 2

    summary = compare_vector_maps(baseline, candidate)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
