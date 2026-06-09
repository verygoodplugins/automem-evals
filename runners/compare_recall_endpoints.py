#!/usr/bin/env python3
"""
Compare /recall behavior across two AutoMem endpoints or against a saved run.

This is for cleanup evaluation: run the same realistic query suite against a
baseline mirror and a cleaned mirror, save raw responses, and report recall
deltas. By default the runner refuses non-local endpoints; use
--allow-non-local only for an intentional production comparison.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

HERE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_HTTP_TIMEOUT_SECONDS = float(
    os.environ.get("RECALL_COMPARE_HTTP_TIMEOUT_SECONDS", "60")
)
DEFAULT_HTTP_RETRIES = int(os.environ.get("RECALL_COMPARE_HTTP_RETRIES", "1"))
DEFAULT_HTTP_RETRY_DELAY_SECONDS = float(
    os.environ.get("RECALL_COMPARE_HTTP_RETRY_DELAY_SECONDS", "1")
)
DEFAULT_TOP_SWAP_REVIEW_EPSILON = float(
    os.environ.get("RECALL_COMPARE_TOP_SWAP_REVIEW_EPSILON", "0.001")
)


def is_local_endpoint(endpoint: str) -> bool:
    parsed = urllib.parse.urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def assert_endpoint_allowed(endpoint: str, allow_non_local: bool) -> None:
    if allow_non_local:
        return
    if not is_local_endpoint(endpoint):
        raise SystemExit(
            f"refusing non-local endpoint without --allow-non-local: {endpoint}"
        )


def endpoint_label(endpoint: str) -> str:
    parsed = urllib.parse.urlparse(endpoint)
    host = parsed.hostname or "unknown"
    port = f"-{parsed.port}" if parsed.port else ""
    return f"{host}{port}".replace(":", "-")


def http_get_json(
    endpoint: str,
    token: str,
    path: str,
    params: dict | None = None,
    *,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    retries: int = DEFAULT_HTTP_RETRIES,
    retry_delay_seconds: float = DEFAULT_HTTP_RETRY_DELAY_SECONDS,
) -> dict:
    flat: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            flat.extend((key, str(item)) for item in value)
        elif isinstance(value, bool):
            flat.append((key, "true" if value else "false"))
        else:
            flat.append((key, str(value)))
    qs = urllib.parse.urlencode(flat)
    url = f"{endpoint.rstrip('/')}{path}"
    if qs:
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"X-Api-Key": token})
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError:
            raise
        except (
            TimeoutError,
            urllib.error.URLError,
            ConnectionError,
            http.client.RemoteDisconnected,
        ):
            if attempt >= retries:
                raise
            attempt += 1
            time.sleep(retry_delay_seconds)


def qdrant_get_payload(
    qdrant_url: str,
    collection: str,
    point_id: str,
    token: str | None = None,
) -> dict:
    endpoint = (
        f"{qdrant_url.rstrip('/')}/collections/"
        f"{urllib.parse.quote(collection)}/points"
    )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["api-key"] = token
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {"ids": [point_id], "with_payload": True, "with_vector": False}
        ).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    points = payload.get("result") or []
    if not points:
        return {}
    return points[0].get("payload") or {}


def qdrant_count_points(
    qdrant_url: str,
    collection: str,
    *,
    timeout_seconds: float = 30,
    retries: int = DEFAULT_HTTP_RETRIES,
    retry_delay_seconds: float = DEFAULT_HTTP_RETRY_DELAY_SECONDS,
) -> int | None:
    endpoint = (
        f"{qdrant_url.rstrip('/')}/collections/" f"{urllib.parse.quote(collection)}"
    )
    req = urllib.request.Request(endpoint)
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                payload = json.loads(response.read())
            break
        except (
            TimeoutError,
            urllib.error.URLError,
            ConnectionError,
            http.client.RemoteDisconnected,
        ):
            if attempt >= retries:
                raise
            attempt += 1
            time.sleep(retry_delay_seconds)
    result = payload.get("result") or {}
    count = result.get("points_count")
    if count is None:
        count = result.get("vectors_count")
    if count is None:
        return None
    return int(count)


def recall(endpoint: str, token: str, query_spec: dict) -> dict:
    params = dict(query_spec.get("params") or {})
    params["query"] = query_spec["query"]
    return http_get_json(endpoint, token, "/recall", params)


def validate_health_pair(baseline_health: dict, candidate_health: dict) -> list[str]:
    errors = []
    for label, health in (
        ("baseline", baseline_health),
        ("candidate", candidate_health),
    ):
        status = health.get("status")
        if status not in {"healthy", "ok"}:
            errors.append(f"{label} health status is not healthy: {status}")
        memory_count = health.get("memory_count")
        vector_count = health.get("vector_count")
        if memory_count != vector_count:
            errors.append(
                f"{label} memory_count/vector_count mismatch: {memory_count} != {vector_count}"
            )
    if baseline_health.get("memory_count") != candidate_health.get("memory_count"):
        errors.append(
            "baseline/candidate memory_count mismatch: "
            f"{baseline_health.get('memory_count')} != {candidate_health.get('memory_count')}"
        )
    if baseline_health.get("vector_count") != candidate_health.get("vector_count"):
        errors.append(
            "baseline/candidate vector_count mismatch: "
            f"{baseline_health.get('vector_count')} != {candidate_health.get('vector_count')}"
        )
    return errors


def recall_has_positive_vector_component(response: dict) -> tuple[bool, dict]:
    results = response.get("results") or []
    vector_values = []
    for result in results:
        score_components = result.get("score_components") or {}
        vector_value = score_components.get("vector") or 0
        try:
            vector_values.append(float(vector_value))
        except (TypeError, ValueError):
            vector_values.append(0.0)
    max_vector = max(vector_values) if vector_values else 0.0
    diagnostic = {
        "returned": len(results),
        "max_vector_component": max_vector,
        "top_ids": [result_id(result) for result in results[:5] if result_id(result)],
    }
    return bool(results and max_vector > 0), diagnostic


def run_preflight(
    *,
    baseline_endpoint: str,
    candidate_endpoint: str,
    token: str,
    probes: list[dict],
    http_get: Callable[[str, str, str, dict | None], dict] | None = None,
    baseline_qdrant_url: str | None = None,
    candidate_qdrant_url: str | None = None,
    qdrant_collection: str = "memories",
    qdrant_count: Callable[[str, str], int | None] = qdrant_count_points,
) -> dict:
    if http_get is None:
        http_get = http_get_json
    baseline_health = http_get(baseline_endpoint, token, "/health", None)
    candidate_health = http_get(candidate_endpoint, token, "/health", None)
    qdrant_count_fallbacks: dict[str, int] = {}
    for label, health, qdrant_url in (
        ("baseline", baseline_health, baseline_qdrant_url),
        ("candidate", candidate_health, candidate_qdrant_url),
    ):
        if health.get("vector_count") is not None or not qdrant_url:
            continue
        try:
            count = qdrant_count(qdrant_url, qdrant_collection)
        except Exception as exc:
            health["vector_count_error"] = str(exc) or exc.__class__.__name__
            continue
        if count is None:
            continue
        health["vector_count"] = count
        health["vector_count_source"] = "qdrant_direct"
        qdrant_count_fallbacks[label] = count
    errors = validate_health_pair(baseline_health, candidate_health)
    warmups = []
    positive_vector_warmups = {"baseline": 0, "candidate": 0}
    nonempty_warmups = {"baseline": 0, "candidate": 0}
    for probe in probes:
        params = dict(probe.get("params") or {})
        params["query"] = probe["query"]
        probe_result = {"id": probe.get("id", "warmup"), "endpoints": {}}
        for label, endpoint in (
            ("baseline", baseline_endpoint),
            ("candidate", candidate_endpoint),
        ):
            response = http_get(endpoint, token, "/recall", params)
            ok, diagnostic = recall_has_positive_vector_component(response)
            probe_result["endpoints"][label] = diagnostic
            if diagnostic["returned"] <= 0:
                errors.append(
                    f"{label} warm-up probe {probe_result['id']} returned no results"
                )
            else:
                nonempty_warmups[label] += 1
            if ok:
                positive_vector_warmups[label] += 1
        warmups.append(probe_result)
    if probes:
        for label in ("baseline", "candidate"):
            if positive_vector_warmups[label] <= 0:
                errors.append(
                    f"{label} had no warm-up probe with a positive vector component"
                )
    return {
        "ok": not errors,
        "errors": errors,
        "baseline_health": baseline_health,
        "candidate_health": candidate_health,
        "warmups": warmups,
        "positive_vector_warmups": positive_vector_warmups,
        "nonempty_warmups": nonempty_warmups,
        "qdrant_count_fallbacks": qdrant_count_fallbacks,
    }


def result_memory(result: dict) -> dict:
    return result.get("memory") or result


def result_id(result: dict) -> str | None:
    return result.get("id") or result.get("memory", {}).get("id")


def result_score(result: dict) -> float | None:
    value = result.get("final_score")
    if value is None:
        value = result.get("score")
    return value


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def passes_tag_filter(tags: list[str], params: dict) -> bool:
    expected = params.get("tags") or []
    if isinstance(expected, str):
        expected = [expected]
    expected_set = {str(tag).lower() for tag in expected if tag}
    if not expected_set:
        return True
    actual_set = {str(tag).lower() for tag in tags if tag}
    mode = str(params.get("tag_mode") or "any").lower()
    if mode == "all":
        return expected_set.issubset(actual_set)
    return bool(expected_set & actual_set)


def _top_result_by_id(summary: dict) -> dict[str, dict]:
    return {item["id"]: item for item in summary.get("top", []) if item.get("id")}


def _first_top_id(summary: dict) -> str | None:
    top_ids = summary.get("top_ids") or [
        item.get("id") for item in summary.get("top", []) if item.get("id")
    ]
    return top_ids[0] if top_ids else None


def _safe_memory_fetch(
    *,
    endpoint: str,
    token: str,
    memory_id: str,
    http_get: Callable[[str, str, str, dict | None], dict],
) -> dict:
    try:
        payload = http_get(endpoint, token, f"/memory/{memory_id}", None)
        return payload.get("memory") or payload
    except Exception as exc:
        return {"error": str(exc)}


def _safe_qdrant_payload_fetch(
    *,
    qdrant_url: str | None,
    collection: str,
    point_id: str,
    qdrant_get: Callable[[str, str, str, str | None], dict],
    token: str | None = None,
) -> dict:
    if not qdrant_url:
        return {"skipped": True}
    try:
        payload = qdrant_get(qdrant_url, collection, point_id, token)
        if isinstance(payload, dict) and "payload" in payload and "tags" not in payload:
            return payload.get("payload") or {}
        return payload
    except Exception as exc:
        return {"error": str(exc)}


def _diagnostic_side(
    *,
    result: dict | None,
    memory: dict,
    qdrant_payload: dict,
    params: dict,
) -> dict:
    result = result or {}
    graph_tags = memory.get("tags") or []
    qdrant_tags = qdrant_payload.get("tags") or []
    result_tags = result.get("tags") or []
    tags = graph_tags or qdrant_tags or result_tags
    return {
        "result": result,
        "score": result.get("score"),
        "original_score": result.get("original_score"),
        "match_type": result.get("match_type"),
        "source": result.get("source"),
        "score_components": result.get("score_components") or {},
        "graph_tags": graph_tags,
        "qdrant_payload_tags": qdrant_tags,
        "qdrant_payload": qdrant_payload,
        "metadata_entities": (memory.get("metadata") or {}).get("entities") or {},
        "graph_passes_tag_filter": passes_tag_filter(graph_tags, params),
        "qdrant_passes_tag_filter": passes_tag_filter(qdrant_tags, params),
        "passes_tag_filter": passes_tag_filter(tags, params),
    }


def write_regression_diagnostics(
    *,
    row: dict,
    baseline_endpoint: str,
    candidate_endpoint: str,
    token: str,
    out_dir: pathlib.Path,
    baseline_qdrant_url: str | None = None,
    candidate_qdrant_url: str | None = None,
    qdrant_collection: str = "memories",
    http_get: Callable[[str, str, str, dict | None], dict] = http_get_json,
    qdrant_get: Callable[[str, str, str, str | None], dict] = qdrant_get_payload,
) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_results = _top_result_by_id(row.get("baseline") or {})
    candidate_results = _top_result_by_id(row.get("candidate") or {})
    params = row.get("params") or {}

    def build_entry(memory_id: str) -> dict[str, Any]:
        baseline_memory = _safe_memory_fetch(
            endpoint=baseline_endpoint,
            token=token,
            memory_id=memory_id,
            http_get=http_get,
        )
        candidate_memory = _safe_memory_fetch(
            endpoint=candidate_endpoint,
            token=token,
            memory_id=memory_id,
            http_get=http_get,
        )
        baseline_payload = _safe_qdrant_payload_fetch(
            qdrant_url=baseline_qdrant_url,
            collection=qdrant_collection,
            point_id=memory_id,
            qdrant_get=qdrant_get,
        )
        candidate_payload = _safe_qdrant_payload_fetch(
            qdrant_url=candidate_qdrant_url,
            collection=qdrant_collection,
            point_id=memory_id,
            qdrant_get=qdrant_get,
        )
        return {
            "id": memory_id,
            "baseline": _diagnostic_side(
                result=baseline_results.get(memory_id),
                memory=baseline_memory,
                qdrant_payload=baseline_payload,
                params=params,
            ),
            "candidate": _diagnostic_side(
                result=candidate_results.get(memory_id),
                memory=candidate_memory,
                qdrant_payload=candidate_payload,
                params=params,
            ),
        }

    diagnostic = {
        "query_id": row["id"],
        "params": params,
        "diff": row.get("diff") or {},
        "changed_top": (
            [
                build_entry(memory_id)
                for memory_id in dict.fromkeys(
                    memory_id
                    for memory_id in (
                        _first_top_id(row.get("baseline") or {}),
                        _first_top_id(row.get("candidate") or {}),
                    )
                    if memory_id
                )
            ]
            if (row.get("diff") or {}).get("top_changed")
            else []
        ),
        "lost": [
            build_entry(memory_id) for memory_id in row["diff"].get("lost_top5", [])
        ],
        "gained": [
            build_entry(memory_id) for memory_id in row["diff"].get("gained_top5", [])
        ],
    }
    out_path = out_dir / f"{row['id']}.json"
    out_path.write_text(json.dumps(diagnostic, indent=2, sort_keys=True) + "\n")
    return out_path


def summarize_response(response: dict, top_n: int = 5) -> dict:
    results = response.get("results") or []
    top = []
    for result in results[:top_n]:
        memory = result_memory(result)
        top.append(
            {
                "id": result_id(result),
                "score": result_score(result),
                "original_score": result.get("original_score"),
                "match_type": result.get("match_type"),
                "source": result.get("source"),
                "score_components": result.get("score_components") or {},
                "tags": memory.get("tags") or [],
                "content": (memory.get("content") or "").replace("\n", " ")[:180],
            }
        )
    return {
        "count": response.get("count", len(results)),
        "returned": len(results),
        "top_ids": [item["id"] for item in top if item["id"]],
        "top": top,
    }


def _score_for_top_id(summary: dict, memory_id: str | None) -> float | None:
    if not memory_id:
        return None
    for item in summary.get("top", []):
        if item.get("id") == memory_id:
            return _as_float(item.get("score"))
    return None


def _near_tie_top_swap(
    baseline: dict,
    candidate: dict,
    *,
    epsilon: float = DEFAULT_TOP_SWAP_REVIEW_EPSILON,
) -> tuple[bool, float | None]:
    baseline_top = baseline["top_ids"]
    candidate_top = candidate["top_ids"]
    if not baseline_top or not candidate_top or baseline_top[0] == candidate_top[0]:
        return False, None
    if any(mid for mid in baseline_top if mid not in candidate_top):
        return False, None
    if any(mid for mid in candidate_top if mid not in baseline_top):
        return False, None

    baseline_first = baseline_top[0]
    candidate_first = candidate_top[0]
    baseline_first_score = _score_for_top_id(baseline, baseline_first)
    baseline_candidate_score = _score_for_top_id(baseline, candidate_first)
    candidate_first_score = _score_for_top_id(candidate, candidate_first)
    candidate_baseline_score = _score_for_top_id(candidate, baseline_first)
    if None in {
        baseline_first_score,
        baseline_candidate_score,
        candidate_first_score,
        candidate_baseline_score,
    }:
        return False, None

    baseline_gap = abs(baseline_first_score - baseline_candidate_score)
    candidate_gap = abs(candidate_first_score - candidate_baseline_score)
    max_gap = max(baseline_gap, candidate_gap)
    return max_gap <= epsilon, max_gap


def diff_summary(baseline: dict, candidate: dict) -> dict:
    baseline_top = baseline["top_ids"]
    candidate_top = candidate["top_ids"]
    top_changed = (baseline_top[0] if baseline_top else None) != (
        candidate_top[0] if candidate_top else None
    )
    near_tie, near_tie_gap = _near_tie_top_swap(baseline, candidate)
    return {
        "count_delta": candidate["count"] - baseline["count"],
        "returned_delta": candidate["returned"] - baseline["returned"],
        "top_changed": top_changed,
        "top_swap_near_tie": near_tie if top_changed else False,
        "top_swap_score_gap": near_tie_gap if top_changed else None,
        "lost_top5": [mid for mid in baseline_top if mid not in candidate_top],
        "gained_top5": [mid for mid in candidate_top if mid not in baseline_top],
    }


def classify_status(group: str, diff: dict) -> str:
    if group == "preserve":
        if diff["count_delta"] < 0:
            return "REGRESSION"
        if diff["lost_top5"]:
            return "REGRESSION"
        if diff["top_changed"] and not diff.get("top_swap_near_tie"):
            return "REGRESSION"
        if diff["top_changed"]:
            return "review"
        return "ok"
    if group == "mixed":
        if diff["count_delta"] < 0 or diff["top_changed"] or diff["lost_top5"]:
            return "review"
        return "ok"
    if group == "noise":
        if diff["count_delta"] < 0:
            return "improved"
        return "observe"
    return "review"


def load_scenario(name_or_path: str) -> dict:
    path = pathlib.Path(name_or_path)
    if not path.exists():
        path = HERE / "scenarios" / f"{name_or_path}.json"
    return json.loads(path.read_text())


def preflight_probes_from_scenario(scenario: dict, limit: int = 2) -> list[dict]:
    queries = scenario.get("queries") or []
    preserve = [query for query in queries if query.get("group") == "preserve"]
    selected = preserve[:limit] or queries[:limit]
    return selected


def write_markdown_report(
    out_path: pathlib.Path,
    scenario: dict,
    baseline_endpoint: str,
    candidate_endpoint: str,
    baseline_health: dict,
    candidate_health: dict,
    rows: list[dict],
    raw_dir: pathlib.Path,
) -> None:
    lines = [
        f"# Recall endpoint comparison - {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Scenario: `{scenario.get('description', '')}`",
        f"Baseline endpoint: `{baseline_endpoint}`",
        f"Candidate endpoint: `{candidate_endpoint}`",
        f"Raw responses: `{raw_dir}`",
        "",
        "## Health",
        "",
        "| Endpoint | status | memory_count | vector_count | sync_status |",
        "|---|---|---:|---:|---|",
        f"| baseline | {baseline_health.get('status')} | {baseline_health.get('memory_count')} | {baseline_health.get('vector_count')} | {baseline_health.get('sync_status')} |",
        f"| candidate | {candidate_health.get('status')} | {candidate_health.get('memory_count')} | {candidate_health.get('vector_count')} | {candidate_health.get('sync_status')} |",
        "",
        "## Summary",
        "",
        "| Query | Group | Status | baseline count | candidate count | delta | top changed | lost top-5 |",
        "|---|---|---|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        diff = row["diff"]
        lines.append(
            "| {id} | {group} | {status} | {bc} | {cc} | {delta} | {top} | {lost} |".format(
                id=row["id"],
                group=row["group"],
                status=row["status"],
                bc=row["baseline"]["count"],
                cc=row["candidate"]["count"],
                delta=diff["count_delta"],
                top=str(diff["top_changed"]).lower(),
                lost=len(diff["lost_top5"]),
            )
        )
    lines.extend(["", "## Details", ""])
    for row in rows:
        lines.append(f"### {row['id']} ({row['group']}, {row['status']})")
        lines.append(row["description"])
        lines.append("")
        lines.append(f"Query: `{row['query']}`")
        lines.append(f"Params: `{json.dumps(row['params'], separators=(',', ':'))}`")
        lines.append("")
        lines.append(f"Diff: `{json.dumps(row['diff'], separators=(',', ':'))}`")
        if row.get("diagnostics"):
            lines.append(f"Diagnostics: `{row['diagnostics']}`")
        lines.append("")
        lines.append("Baseline top:")
        for index, item in enumerate(row["baseline"]["top"][:3], start=1):
            lines.append(f"{index}. `{item['id']}` [{item['score']}] {item['content']}")
        lines.append("")
        lines.append("Candidate top:")
        for index, item in enumerate(row["candidate"]["top"][:3], start=1):
            lines.append(f"{index}. `{item['id']}` [{item['score']}] {item['content']}")
        lines.append("")
    out_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--scenario", default="recall_cleanup_v1")
    parser.add_argument("--baseline-endpoint", default=None)
    parser.add_argument(
        "--baseline-summary",
        default=None,
        help="Compare candidate results against a saved summary.json from a previous run.",
    )
    parser.add_argument("--candidate-endpoint", required=True)
    parser.add_argument("--token", default="test-token")
    parser.add_argument("--allow-non-local", action="store_true")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--fail-on-preserve-regression", action="store_true")
    parser.add_argument(
        "--fail-on-preserve-review",
        action="store_true",
        help=(
            "Fail when any preserve probe is not ok, including review-level "
            "top-5 churn. Use for production-readiness gates."
        ),
    )
    parser.add_argument("--skip-vector-preflight", action="store_true")
    parser.add_argument("--baseline-qdrant-url", default=None)
    parser.add_argument("--candidate-qdrant-url", default=None)
    parser.add_argument("--qdrant-collection", default="memories")
    args = parser.parse_args()

    if not args.baseline_endpoint and not args.baseline_summary:
        raise SystemExit("one of --baseline-endpoint or --baseline-summary is required")
    if args.baseline_endpoint:
        assert_endpoint_allowed(args.baseline_endpoint, args.allow_non_local)
    assert_endpoint_allowed(args.candidate_endpoint, args.allow_non_local)

    scenario = load_scenario(args.scenario)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = (
        pathlib.Path(args.run_dir)
        if args.run_dir
        else HERE
        / "data"
        / "sweep_runs"
        / (
            f"{timestamp}-recall-compare-"
            f"{endpoint_label(args.baseline_endpoint) if args.baseline_endpoint else 'saved-baseline'}"
            f"-vs-{endpoint_label(args.candidate_endpoint)}"
        )
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    diagnostics_dir = run_dir / "diagnostics"

    saved_rows_by_id: dict[str, dict] = {}
    saved_baseline_endpoint = args.baseline_endpoint or "saved baseline"
    if args.baseline_summary:
        saved = json.loads(pathlib.Path(args.baseline_summary).read_text())
        baseline_health = (
            saved.get("baseline_health") or saved.get("candidate_health") or {}
        )
        saved_baseline_endpoint = (
            saved.get("baseline_endpoint")
            or saved.get("candidate_endpoint")
            or saved_baseline_endpoint
        )
        saved_rows_by_id = {row["id"]: row for row in saved.get("rows", [])}
    else:
        baseline_health = http_get_json(args.baseline_endpoint, args.token, "/health")
    candidate_health = http_get_json(args.candidate_endpoint, args.token, "/health")
    (run_dir / "baseline-health.json").write_text(json.dumps(baseline_health, indent=2))
    (run_dir / "candidate-health.json").write_text(
        json.dumps(candidate_health, indent=2)
    )

    if args.baseline_endpoint and not args.skip_vector_preflight:
        preflight = run_preflight(
            baseline_endpoint=args.baseline_endpoint,
            candidate_endpoint=args.candidate_endpoint,
            token=args.token,
            probes=preflight_probes_from_scenario(scenario),
            baseline_qdrant_url=args.baseline_qdrant_url,
            candidate_qdrant_url=args.candidate_qdrant_url,
            qdrant_collection=args.qdrant_collection,
        )
        (run_dir / "preflight.json").write_text(json.dumps(preflight, indent=2))
        if not preflight["ok"]:
            (run_dir / "preflight-failed.json").write_text(
                json.dumps(preflight, indent=2)
            )
            print(f"preflight failed: {run_dir / 'preflight-failed.json'}")
            return 2

    rows = []
    for spec in scenario["queries"]:
        qid = spec["id"]
        try:
            if saved_rows_by_id:
                saved_row = saved_rows_by_id.get(qid)
                if not saved_row:
                    raise SystemExit(f"baseline summary missing query id: {qid}")
                baseline_summary = saved_row.get("candidate") or saved_row.get(
                    "baseline"
                )
                if not baseline_summary:
                    raise SystemExit(
                        f"baseline summary has no saved result for query id: {qid}"
                    )
                baseline_response = None
            else:
                baseline_response = recall(args.baseline_endpoint, args.token, spec)
            candidate_response = recall(args.candidate_endpoint, args.token, spec)
        except Exception as exc:
            failure = {
                "ok": False,
                "stage": "recall",
                "query_id": qid,
                "query": spec.get("query"),
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "rows_completed": len(rows),
                "completed_query_ids": [row["id"] for row in rows],
            }
            (run_dir / "comparison-failed.json").write_text(
                json.dumps(failure, indent=2)
            )
            print(f"comparison failed: {run_dir / 'comparison-failed.json'}")
            return 2
        if baseline_response is not None:
            (raw_dir / f"{qid}.baseline.json").write_text(
                json.dumps(baseline_response, indent=2)
            )
        (raw_dir / f"{qid}.candidate.json").write_text(
            json.dumps(candidate_response, indent=2)
        )
        if baseline_response is not None:
            baseline_summary = summarize_response(baseline_response)
        candidate_summary = summarize_response(candidate_response)
        diff = diff_summary(baseline_summary, candidate_summary)
        group = spec.get("group", "mixed")
        rows.append(
            {
                "id": qid,
                "group": group,
                "description": spec.get("description", ""),
                "query": spec["query"],
                "params": spec.get("params") or {},
                "baseline": baseline_summary,
                "candidate": candidate_summary,
                "diff": diff,
                "status": classify_status(group, diff),
            }
        )
        if args.baseline_endpoint and (
            diff["top_changed"] or diff["lost_top5"] or diff["gained_top5"]
        ):
            diagnostics_path = write_regression_diagnostics(
                row=rows[-1],
                baseline_endpoint=args.baseline_endpoint,
                candidate_endpoint=args.candidate_endpoint,
                token=args.token,
                out_dir=diagnostics_dir,
                baseline_qdrant_url=args.baseline_qdrant_url,
                candidate_qdrant_url=args.candidate_qdrant_url,
                qdrant_collection=args.qdrant_collection,
            )
            rows[-1]["diagnostics"] = str(
                diagnostics_path.relative_to(HERE)
                if diagnostics_path.is_relative_to(HERE)
                else diagnostics_path
            )
        print(
            f"{qid}: {rows[-1]['status']} "
            f"{baseline_summary['count']}->{candidate_summary['count']} "
            f"top_changed={diff['top_changed']} lost_top5={len(diff['lost_top5'])}"
        )

    summary = {
        "scenario": args.scenario,
        "baseline_endpoint": saved_baseline_endpoint,
        "baseline_summary": args.baseline_summary,
        "candidate_endpoint": args.candidate_endpoint,
        "baseline_health": baseline_health,
        "candidate_health": candidate_health,
        "rows": rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    report_path = (
        pathlib.Path(args.report)
        if args.report
        else HERE / "data" / "results" / f"{timestamp}-recall-endpoint-comparison.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_report(
        report_path,
        scenario,
        saved_baseline_endpoint,
        args.candidate_endpoint,
        baseline_health,
        candidate_health,
        rows,
        raw_dir.relative_to(HERE) if raw_dir.is_relative_to(HERE) else raw_dir,
    )
    print(
        f"summary: {run_dir.relative_to(HERE) if run_dir.is_relative_to(HERE) else run_dir}/summary.json"
    )
    print(
        f"report: {report_path.relative_to(HERE) if report_path.is_relative_to(HERE) else report_path}"
    )

    preserve_failures = [
        row for row in rows if row["group"] == "preserve" and row["status"] != "ok"
    ]
    if args.fail_on_preserve_review and preserve_failures:
        print(
            "preserve review gate failed: "
            + ", ".join(row["id"] for row in preserve_failures)
        )
        return 1
    if args.fail_on_preserve_regression and any(
        row["status"] == "REGRESSION" for row in preserve_failures
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
