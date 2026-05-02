#!/usr/bin/env python3
"""Run a recall-quality matrix across local AutoMem endpoints and rulesets.

Each endpoint represents a storage/database variant. Each ruleset represents a
recall strategy. The runner executes every endpoint x ruleset x scenario cell
in parallel, scores results with the same manifest logic as compare_rulesets.py,
and writes JSON + markdown artifacts under data/results/matrix/.

This is intentionally a coordinator over existing harness pieces, not a Docker
provisioner. Start isolated AutoMem stacks separately, then pass them here:

  python3 runners/run_matrix.py \
    --endpoint baseline=http://localhost:8001 \
    --endpoint atomic=http://localhost:8011 \
    --rulesets bare_tag_1m_v2 iso_h_v2_no_gate \
    --scenarios session_start_v2 \
    --manifest corpus_v2.manifest.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import compare_rulesets as cr

HERE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = HERE / "data" / "results" / "matrix"
DEFAULT_TOKEN = "test-token"


@dataclass(frozen=True)
class EndpointSpec:
    label: str
    url: str


@dataclass(frozen=True)
class MatrixTask:
    endpoint: EndpointSpec
    ruleset_name: str
    scenario: dict[str, Any]


def is_local_endpoint(endpoint: str) -> bool:
    parsed = urllib.parse.urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def parse_endpoint(value: str) -> EndpointSpec:
    if "=" not in value:
        raise ValueError(f"endpoint must be label=url, got: {value!r}")
    label, url = value.split("=", 1)
    label = label.strip()
    url = url.strip().rstrip("/")
    if not label:
        raise ValueError("endpoint label cannot be empty")
    if not url:
        raise ValueError("endpoint url cannot be empty")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"endpoint url must be absolute http(s), got: {url!r}")
    return EndpointSpec(label=label, url=url)


def parse_endpoints(values: list[str]) -> list[EndpointSpec]:
    endpoints = [parse_endpoint(value) for value in values]
    labels = [endpoint.label for endpoint in endpoints]
    if len(set(labels)) != len(labels):
        raise ValueError("endpoint labels must be unique")
    return endpoints


def assert_endpoints_allowed(endpoints: list[EndpointSpec], allow_non_local: bool) -> None:
    if allow_non_local:
        return
    remote = [endpoint for endpoint in endpoints if not is_local_endpoint(endpoint.url)]
    if remote:
        formatted = ", ".join(f"{e.label}={e.url}" for e in remote)
        raise SystemExit(f"refusing non-local endpoint(s) without --allow-non-local: {formatted}")


def http_get_json(endpoint: str, token: str, path: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}{path}",
        headers={"X-Api-Key": token},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def health_check(endpoint: EndpointSpec, token: str) -> dict:
    health = http_get_json(endpoint.url, token, "/health")
    if health.get("status") != "healthy":
        raise RuntimeError(f"{endpoint.label} unhealthy: {health!r}")
    return health


def build_tasks(
    endpoints: list[EndpointSpec],
    ruleset_names: list[str],
    scenarios: list[dict[str, Any]],
) -> list[MatrixTask]:
    return [
        MatrixTask(endpoint=endpoint, ruleset_name=ruleset_name, scenario=scenario)
        for endpoint in endpoints
        for ruleset_name in ruleset_names
        for scenario in scenarios
    ]


def run_task(
    task: MatrixTask,
    token: str,
    rulesets: dict[str, dict],
    manifest: dict,
) -> dict:
    started = time.monotonic()
    try:
        run = cr.run_phase(
            task.endpoint.url,
            token,
            rulesets[task.ruleset_name],
            task.scenario["phase"],
            task.scenario,
        )
        metrics = cr.score_scenario(run, task.scenario, manifest)
        status = "ok"
        error = None
    except Exception as exc:  # fail per cell; the report must show holes
        run = {"params": {}, "response": {"results": []}}
        metrics = {
            "results_returned": 0,
            "expected_in_corpus": 0,
            "hits_total": 0,
            "hits_in_top_k": 0,
            "precision_at_k": 0.0,
            "recall": 0.0,
            "rank_of_first_hit": None,
            "top_score": None,
        }
        status = "error"
        error = str(exc)

    return {
        "endpoint": task.endpoint.label,
        "endpoint_url": task.endpoint.url,
        "ruleset": task.ruleset_name,
        "scenario_id": task.scenario["id"],
        "phase": task.scenario["phase"],
        "status": status,
        "error": error,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "params": run["params"],
        "metrics": metrics,
        "top": summarize_top_results(run["response"], limit=5),
    }


def summarize_top_results(response: dict, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    for item in (response.get("results") or [])[:limit]:
        memory = item.get("memory") or item
        out.append(
            {
                "id": item.get("id") or memory.get("id") or memory.get("memory_id"),
                "score": item.get("final_score") or item.get("score"),
                "tags": memory.get("tags") or [],
                "content": (memory.get("content") or "").replace("\n", " ")[:180],
            }
        )
    return out


def aggregate_results(rows: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        buckets.setdefault((row["endpoint"], row["ruleset"]), []).append(row)

    out = []
    for (endpoint, ruleset), bucket in sorted(buckets.items()):
        scenario_count = len(bucket)
        error_count = sum(1 for row in bucket if row["status"] != "ok")
        expected = sum(row["metrics"]["expected_in_corpus"] for row in bucket)
        hits = sum(row["metrics"]["hits_total"] for row in bucket)
        p_at_5 = sum(row["metrics"]["precision_at_k"] for row in bucket) / max(scenario_count, 1)
        recall = hits / max(expected, 1)
        first_ranks = [
            row["metrics"]["rank_of_first_hit"]
            for row in bucket
            if row["metrics"]["rank_of_first_hit"] is not None
        ]
        out.append(
            {
                "endpoint": endpoint,
                "ruleset": ruleset,
                "scenarios": scenario_count,
                "errors": error_count,
                "hits": hits,
                "expected": expected,
                "recall": recall,
                "mean_precision_at_5": p_at_5,
                "mean_first_hit_rank": (
                    sum(first_ranks) / len(first_ranks) if first_ranks else None
                ),
            }
        )
    return out


def render_markdown(run: dict) -> str:
    lines = [
        f"# Recall matrix - {run['generated_at']}",
        "",
        f"Scenarios: `{run['scenarios_name']}`",
        f"Manifest: `{run['manifest_name']}`",
        f"Raw JSON: `{run['json_path']}`",
        "",
        "## Endpoints",
        "",
        "| Label | URL | status | memory_count | vector_count | sync |",
        "|---|---|---|---:|---:|---|",
    ]
    for endpoint in run["endpoints"]:
        health = run["health"].get(endpoint["label"], {})
        lines.append(
            "| {label} | `{url}` | {status} | {memories} | {vectors} | {sync} |".format(
                label=endpoint["label"],
                url=endpoint["url"],
                status=health.get("status", "error"),
                memories=health.get("memory_count", ""),
                vectors=health.get("vector_count", ""),
                sync=health.get("sync_status", ""),
            )
        )

    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            "| Endpoint | Ruleset | Scenarios | Errors | Hits | Expected | Recall | Mean P@5 | Mean rank1 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in run["aggregate"]:
        rank = row["mean_first_hit_rank"]
        lines.append(
            "| {endpoint} | {ruleset} | {scenarios} | {errors} | {hits} | {expected} | {recall:.3f} | {p5:.3f} | {rank} |".format(
                endpoint=row["endpoint"],
                ruleset=row["ruleset"],
                scenarios=row["scenarios"],
                errors=row["errors"],
                hits=row["hits"],
                expected=row["expected"],
                recall=row["recall"],
                p5=row["mean_precision_at_5"],
                rank=f"{rank:.2f}" if rank is not None else "-",
            )
        )

    lines.extend(["", "## Cells", ""])
    for row in sorted(run["rows"], key=lambda r: (r["endpoint"], r["ruleset"], r["scenario_id"])):
        m = row["metrics"]
        err = f" ERROR: {row['error']}" if row["error"] else ""
        lines.append(
            "- `{endpoint}` / `{ruleset}` / `{scenario}`: {status}{err}; "
            "hits {hits}/{expected}, P@5 {p5:.2f}, rank1 {rank}".format(
                endpoint=row["endpoint"],
                ruleset=row["ruleset"],
                scenario=row["scenario_id"],
                status=row["status"],
                err=err,
                hits=m["hits_total"],
                expected=m["expected_in_corpus"],
                p5=m["precision_at_k"],
                rank=m["rank_of_first_hit"] or "-",
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(
    run_obj: dict,
    results_dir: pathlib.Path,
    timestamp: str,
) -> tuple[pathlib.Path, pathlib.Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"{timestamp}-matrix.json"
    md_path = results_dir / f"{timestamp}-matrix.md"
    run_obj["json_path"] = display_path(json_path)
    json_path.write_text(json.dumps(run_obj, indent=2, default=str))
    md_path.write_text(render_markdown(run_obj))
    return json_path, md_path


def display_path(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(HERE))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--endpoint",
        action="append",
        required=True,
        help="Local endpoint as label=url. Repeat for each storage/database variant.",
    )
    parser.add_argument("--rulesets", nargs="+", default=["baseline_v1", "bare_tag_1m_v2"])
    parser.add_argument("--scenarios", default="session_start_v1")
    parser.add_argument("--manifest", default="corpus_v1.manifest.json")
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--results-dir", type=pathlib.Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--allow-non-local", action="store_true")
    args = parser.parse_args(argv)

    endpoints = parse_endpoints(args.endpoint)
    assert_endpoints_allowed(endpoints, args.allow_non_local)

    manifest = cr.load_manifest(args.manifest)
    scenario_set = cr.load_scenarios(args.scenarios)
    rulesets = {name: cr.load_ruleset(name) for name in args.rulesets}

    print(f"health checking {len(endpoints)} endpoint(s)")
    health: dict[str, dict] = {}
    for endpoint in endpoints:
        health[endpoint.label] = health_check(endpoint, args.token)
        print(
            f"  {endpoint.label}: {health[endpoint.label].get('status')} "
            f"memories={health[endpoint.label].get('memory_count')}"
        )

    tasks = build_tasks(endpoints, args.rulesets, scenario_set["scenarios"])
    print(
        f"running {len(tasks)} cells "
        f"({len(endpoints)} endpoint(s) x {len(args.rulesets)} ruleset(s) x {len(scenario_set['scenarios'])} scenario(s))"
    )

    rows: list[dict] = []
    max_workers = max(1, min(args.workers, len(tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(run_task, task, args.token, rulesets, manifest) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            m = row["metrics"]
            print(
                f"  {row['endpoint']}/{row['ruleset']}/{row['scenario_id']}: "
                f"{row['status']} hits={m['hits_total']}/{m['expected_in_corpus']} "
                f"P@5={m['precision_at_k']:.2f}"
            )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_obj = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoints": [{"label": e.label, "url": e.url} for e in endpoints],
        "rulesets": args.rulesets,
        "scenarios_name": args.scenarios,
        "manifest_name": args.manifest,
        "health": health,
        "rows": rows,
        "aggregate": aggregate_results(rows),
        "json_path": "",
    }
    json_path, md_path = write_artifacts(run_obj, args.results_dir, timestamp)
    print(f"json:   {display_path(json_path)}")
    print(f"report: {display_path(md_path)}")

    return 1 if any(row["status"] != "ok" for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
