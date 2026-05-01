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
import json
import pathlib
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent


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


def http_get_json(endpoint: str, token: str, path: str, params: dict | None = None) -> dict:
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
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def recall(endpoint: str, token: str, query_spec: dict) -> dict:
    params = dict(query_spec.get("params") or {})
    params["query"] = query_spec["query"]
    return http_get_json(endpoint, token, "/recall", params)


def result_memory(result: dict) -> dict:
    return result.get("memory") or result


def result_id(result: dict) -> str | None:
    return result.get("id") or result.get("memory", {}).get("id")


def result_score(result: dict) -> float | None:
    value = result.get("final_score")
    if value is None:
        value = result.get("score")
    return value


def summarize_response(response: dict, top_n: int = 5) -> dict:
    results = response.get("results") or []
    top = []
    for result in results[:top_n]:
        memory = result_memory(result)
        top.append(
            {
                "id": result_id(result),
                "score": result_score(result),
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


def diff_summary(baseline: dict, candidate: dict) -> dict:
    baseline_top = baseline["top_ids"]
    candidate_top = candidate["top_ids"]
    return {
        "count_delta": candidate["count"] - baseline["count"],
        "returned_delta": candidate["returned"] - baseline["returned"],
        "top_changed": (baseline_top[0] if baseline_top else None)
        != (candidate_top[0] if candidate_top else None),
        "lost_top5": [mid for mid in baseline_top if mid not in candidate_top],
        "gained_top5": [mid for mid in candidate_top if mid not in baseline_top],
    }


def classify_status(group: str, diff: dict) -> str:
    if group == "preserve":
        if diff["count_delta"] < 0 or diff["top_changed"] or diff["lost_top5"]:
            return "REGRESSION"
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
        lines.append(
            f"Diff: `{json.dumps(row['diff'], separators=(',', ':'))}`"
        )
        lines.append("")
        lines.append("Baseline top:")
        for index, item in enumerate(row["baseline"]["top"][:3], start=1):
            lines.append(
                f"{index}. `{item['id']}` [{item['score']}] {item['content']}"
            )
        lines.append("")
        lines.append("Candidate top:")
        for index, item in enumerate(row["candidate"]["top"][:3], start=1):
            lines.append(
                f"{index}. `{item['id']}` [{item['score']}] {item['content']}"
            )
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

    saved_rows_by_id: dict[str, dict] = {}
    saved_baseline_endpoint = args.baseline_endpoint or "saved baseline"
    if args.baseline_summary:
        saved = json.loads(pathlib.Path(args.baseline_summary).read_text())
        baseline_health = saved.get("baseline_health") or saved.get("candidate_health") or {}
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
    (run_dir / "candidate-health.json").write_text(json.dumps(candidate_health, indent=2))

    rows = []
    for spec in scenario["queries"]:
        qid = spec["id"]
        if saved_rows_by_id:
            saved_row = saved_rows_by_id.get(qid)
            if not saved_row:
                raise SystemExit(f"baseline summary missing query id: {qid}")
            baseline_summary = saved_row.get("candidate") or saved_row.get("baseline")
            if not baseline_summary:
                raise SystemExit(f"baseline summary has no saved result for query id: {qid}")
            baseline_response = None
        else:
            baseline_response = recall(args.baseline_endpoint, args.token, spec)
        candidate_response = recall(args.candidate_endpoint, args.token, spec)
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
    print(f"summary: {run_dir.relative_to(HERE) if run_dir.is_relative_to(HERE) else run_dir}/summary.json")
    print(f"report: {report_path.relative_to(HERE) if report_path.is_relative_to(HERE) else report_path}")

    if args.fail_on_preserve_regression and any(
        row["status"] == "REGRESSION" for row in rows
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
