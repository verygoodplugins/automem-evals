#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.parse
import urllib.request
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TOKEN = "test-token"


def is_local_endpoint(endpoint: str) -> bool:
    parsed = urllib.parse.urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def assert_local_endpoint(endpoint: str) -> None:
    if not is_local_endpoint(endpoint):
        raise SystemExit(f"refusing non-local endpoint: {endpoint}")


def http_get_json(endpoint: str, token: str, path: str, params: dict[str, Any] | None = None) -> dict:
    pairs: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            pairs.extend((key, str(item)) for item in value)
        elif isinstance(value, bool):
            pairs.append((key, "true" if value else "false"))
        else:
            pairs.append((key, str(value)))
    query = urllib.parse.urlencode(pairs)
    url = f"{endpoint.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, headers={"X-Api-Key": token})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def recall(endpoint: str, token: str, scenario: dict[str, Any]) -> dict:
    params = dict(scenario.get("params") or {})
    params["query"] = scenario["query"]
    return http_get_json(endpoint, token, "/recall", params)


def result_id(result: dict[str, Any]) -> str | None:
    memory = result.get("memory") or {}
    value = result.get("id") or memory.get("id") or memory.get("memory_id")
    return str(value) if value else None


def rank_expected_ids(response: dict[str, Any], expected_ids: set[str]) -> tuple[int | None, list[str]]:
    found: list[str] = []
    first_rank: int | None = None
    for index, result in enumerate(response.get("results") or [], start=1):
        memory_id = result_id(result)
        if memory_id and memory_id in expected_ids:
            found.append(memory_id)
            if first_rank is None:
                first_rank = index
    return first_rank, found


def _score_side(response: dict[str, Any], expected_ids: set[str]) -> dict[str, Any]:
    rank, found = rank_expected_ids(response, expected_ids)
    vector_nonzero = 0
    for result in response.get("results") or []:
        components = result.get("score_components") or {}
        try:
            if float(components.get("vector") or 0.0) > 0:
                vector_nonzero += 1
        except (TypeError, ValueError):
            pass
    return {
        "rank": rank,
        "found_ids": found,
        "hit_at_1": rank is not None and rank <= 1,
        "hit_at_5": rank is not None and rank <= 5,
        "hit_at_10": rank is not None and rank <= 10,
        "mrr": (1.0 / rank) if rank else 0.0,
        "returned": len(response.get("results") or []),
        "vector_nonzero_results": vector_nonzero,
    }


def _top_k_expected_ids(response: dict[str, Any], expected_ids: set[str], k: int) -> set[str]:
    out: set[str] = set()
    for result in (response.get("results") or [])[:k]:
        memory_id = result_id(result)
        if memory_id in expected_ids:
            out.add(memory_id)
    return out


def score_pair(
    scenario: dict[str, Any],
    baseline_response: dict[str, Any],
    candidate_response: dict[str, Any],
) -> dict[str, Any]:
    expected_ids = {str(item) for item in scenario.get("expected_ids") or []}
    baseline = _score_side(baseline_response, expected_ids)
    candidate = _score_side(candidate_response, expected_ids)
    baseline_top10 = _top_k_expected_ids(baseline_response, expected_ids, 10)
    candidate_top10 = _top_k_expected_ids(candidate_response, expected_ids, 10)
    rank_delta = (
        candidate["rank"] - baseline["rank"]
        if candidate["rank"] is not None and baseline["rank"] is not None
        else None
    )
    return {
        "id": scenario["id"],
        "expected_field": scenario.get("expected_field", ""),
        "expected_value": scenario.get("expected_value", ""),
        "expected_ids": sorted(expected_ids),
        "query": scenario.get("query", ""),
        "params": scenario.get("params") or {},
        "baseline": baseline,
        "candidate": candidate,
        "rank_delta": rank_delta,
        "gained_ids": sorted(candidate_top10 - baseline_top10),
        "lost_ids": sorted(baseline_top10 - candidate_top10),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate_side(rows: list[dict[str, Any]], side: str) -> dict[str, Any]:
    count = max(len(rows), 1)
    side_rows = [row.get(side) or {} for row in rows]
    ranks = [row.get("rank") for row in side_rows if row.get("rank") is not None]
    return {
        "hit_at_1": sum(1 for row in side_rows if row.get("hit_at_1")) / count,
        "hit_at_5": sum(1 for row in side_rows if row.get("hit_at_5")) / count,
        "hit_at_10": sum(1 for row in side_rows if row.get("hit_at_10")) / count,
        "mrr": _mean([float(row.get("mrr") or 0.0) for row in side_rows]),
        "mean_target_rank": _mean([float(rank) for rank in ranks]),
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_field: dict[str, dict[str, Any]] = {}
    fields = sorted({row.get("expected_field", "") for row in rows})
    for field in fields:
        bucket = [row for row in rows if row.get("expected_field", "") == field]
        baseline = _aggregate_side(bucket, "baseline")
        candidate = _aggregate_side(bucket, "candidate")
        per_field[field] = {
            "scenario_count": len(bucket),
            "baseline_hit_at_5": baseline["hit_at_5"],
            "candidate_hit_at_5": candidate["hit_at_5"],
            "hit_at_5_delta": candidate["hit_at_5"] - baseline["hit_at_5"],
            "mrr_delta": candidate["mrr"] - baseline["mrr"],
        }
    baseline = _aggregate_side(rows, "baseline")
    candidate = _aggregate_side(rows, "candidate")
    return {
        "scenario_count": len(rows),
        "baseline": baseline,
        "candidate": candidate,
        "hit_at_5_delta": candidate["hit_at_5"] - baseline["hit_at_5"],
        "mrr_delta": candidate["mrr"] - baseline["mrr"],
        "gained_expected_id_count": sum(len(row["gained_ids"]) for row in rows),
        "lost_expected_id_count": sum(len(row["lost_ids"]) for row in rows),
        "per_field": per_field,
    }


def load_scenarios(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    scenarios = data.get("scenarios") or data.get("queries") or []
    if not isinstance(scenarios, list):
        raise ValueError("scenario file must contain a scenarios list")
    return scenarios


def load_warmup_queries(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    warmups = data.get("warmup_queries") or []
    if not isinstance(warmups, list):
        raise ValueError("scenario file warmup_queries must be a list")
    return warmups


def vector_warmup(
    endpoint: str,
    token: str,
    scenarios: list[dict[str, Any]],
    *,
    sample_count: int = 3,
) -> dict[str, Any]:
    checked = 0
    nonzero = 0
    samples: list[dict[str, Any]] = []
    for scenario in scenarios[:sample_count]:
        response = recall(endpoint, token, scenario)
        checked += 1
        values: list[float] = []
        for result in response.get("results") or []:
            components = result.get("score_components") or {}
            try:
                value = float(components.get("vector") or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            values.append(value)
            if value > 0:
                nonzero += 1
        samples.append({"id": scenario["id"], "vector_components": values[:5]})
    status = "ok" if nonzero > 0 else ("skipped" if checked == 0 else "failed")
    return {"status": status, "checked": checked, "nonzero_results": nonzero, "samples": samples}


def write_markdown_report(
    path: pathlib.Path,
    *,
    baseline_endpoint: str,
    candidate_endpoint: str,
    aggregate: dict[str, Any],
    rows: list[dict[str, Any]],
    vector_preflight: dict[str, Any],
) -> None:
    lines = [
        f"# Metadata A/B report - {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Baseline endpoint: `{baseline_endpoint}`",
        f"Candidate endpoint: `{candidate_endpoint}`",
        "",
        "## Vector Preflight",
        "",
        "| Endpoint | status | checked | nonzero results |",
        "|---|---|---:|---:|",
    ]
    for label in ("baseline", "candidate"):
        item = vector_preflight.get(label) or {}
        lines.append(
            f"| {label} | {item.get('status')} | {item.get('checked', 0)} | {item.get('nonzero_results', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            "| Metric | Baseline | Candidate | Delta |",
            "|---|---:|---:|---:|",
            f"| hit@5 | {aggregate['baseline']['hit_at_5']:.3f} | {aggregate['candidate']['hit_at_5']:.3f} | {aggregate['hit_at_5_delta']:.3f} |",
            f"| MRR | {aggregate['baseline']['mrr']:.3f} | {aggregate['candidate']['mrr']:.3f} | {aggregate['mrr_delta']:.3f} |",
            f"| mean target rank | {aggregate['baseline']['mean_target_rank']:.3f} | {aggregate['candidate']['mean_target_rank']:.3f} | |",
            "",
            "## Probe Rows",
            "",
            "| Scenario | Field | Baseline rank | Candidate rank | Gained | Lost |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            "| {id} | {field} | {br} | {cr} | {g} | {l} |".format(
                id=row["id"],
                field=row["expected_field"],
                br=row["baseline"]["rank"] or "",
                cr=row["candidate"]["rank"] or "",
                g=len(row["gained_ids"]),
                l=len(row["lost_ids"]),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def merge_vector_preflight(path: pathlib.Path, recall_warmup: dict[str, Any]) -> dict[str, Any]:
    transform_preflight: dict[str, Any] | None = None
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = None
        if isinstance(existing, dict):
            transform_preflight = existing
    if transform_preflight is None:
        return {"recall_warmup": recall_warmup}
    return {"transform": transform_preflight, "recall_warmup": recall_warmup}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run metadata-specific A/B recall eval")
    parser.add_argument("--scenario", required=True, type=pathlib.Path)
    parser.add_argument("--baseline-endpoint", required=True)
    parser.add_argument("--candidate-endpoint", required=True)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--run-dir", type=pathlib.Path, default=None)
    parser.add_argument("--report", type=pathlib.Path, default=None)
    parser.add_argument("--metrics-output", type=pathlib.Path, default=None)
    args = parser.parse_args()

    assert_local_endpoint(args.baseline_endpoint)
    assert_local_endpoint(args.candidate_endpoint)

    scenarios = load_scenarios(args.scenario)
    warmup_queries = load_warmup_queries(args.scenario) or scenarios
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or HERE / "data" / "sweep_runs" / f"{timestamp}-metadata-ab"
    raw_dir = run_dir / "raw" / "metadata-ab"
    raw_dir.mkdir(parents=True, exist_ok=True)

    baseline_health = http_get_json(args.baseline_endpoint, args.token, "/health")
    candidate_health = http_get_json(args.candidate_endpoint, args.token, "/health")
    recall_warmup = {
        "baseline": vector_warmup(args.baseline_endpoint, args.token, warmup_queries),
        "candidate": vector_warmup(args.candidate_endpoint, args.token, warmup_queries),
    }
    if scenarios and (
        recall_warmup["baseline"]["status"] != "ok"
        or recall_warmup["candidate"]["status"] != "ok"
    ):
        preflight_path = run_dir / "vector_preflight.json"
        preflight_payload = merge_vector_preflight(preflight_path, recall_warmup)
        preflight_path.write_text(json.dumps(preflight_payload, indent=2) + "\n")
        raise SystemExit("vector warmup failed; refusing to compare recall deltas")

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        baseline_response = recall(args.baseline_endpoint, args.token, scenario)
        candidate_response = recall(args.candidate_endpoint, args.token, scenario)
        (raw_dir / f"{scenario['id']}.baseline.json").write_text(
            json.dumps(baseline_response, indent=2) + "\n"
        )
        (raw_dir / f"{scenario['id']}.candidate.json").write_text(
            json.dumps(candidate_response, indent=2) + "\n"
        )
        rows.append(score_pair(scenario, baseline_response, candidate_response))

    aggregate = aggregate_rows(rows)
    preflight_path = run_dir / "vector_preflight.json"
    vector_preflight = merge_vector_preflight(preflight_path, recall_warmup)
    metrics = {
        "baseline_endpoint": args.baseline_endpoint,
        "candidate_endpoint": args.candidate_endpoint,
        "baseline_health": baseline_health,
        "candidate_health": candidate_health,
        "vector_preflight": vector_preflight,
        "aggregate": aggregate,
        "rows": rows,
    }

    metrics_path = args.metrics_output or run_dir / "metadata-ab-metrics.json"
    report_path = args.report or run_dir / "metadata-ab-report.md"
    preflight_path.write_text(json.dumps(vector_preflight, indent=2) + "\n")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    write_markdown_report(
        report_path,
        baseline_endpoint=args.baseline_endpoint,
        candidate_endpoint=args.candidate_endpoint,
        aggregate=aggregate,
        rows=rows,
        vector_preflight=recall_warmup,
    )
    print(f"metrics: {metrics_path}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
