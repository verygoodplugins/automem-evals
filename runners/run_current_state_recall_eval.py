#!/usr/bin/env python3
"""
Seed and evaluate AutoMem current-state recall behavior.

This runner is intentionally narrow: it creates isolated memories that exercise
temporal validity and supersession semantics, probes /recall, writes raw
responses plus a markdown report, and then deletes the seeded memories by run
tag unless --keep-data is set.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
BASE_TAG = "pr170-current-state-eval"


@dataclass(frozen=True)
class MemoryFixture:
    key: str
    content: str
    tags: list[str]
    importance: float
    memory_type: str = "Context"
    confidence: float = 0.9
    t_valid_offset_days: int | None = None
    t_invalid_offset_days: int | None = None


@dataclass(frozen=True)
class RelationFixture:
    source_key: str
    target_key: str
    relation_type: str
    strength: float = 0.9


@dataclass(frozen=True)
class Probe:
    id: str
    query: str
    params: dict[str, Any]
    current_present: list[str]
    current_absent: list[str]
    unfiltered_present: list[str]
    expect_mode: str | None = None
    min_suppressed_current: int = 0


FIXTURES: list[MemoryFixture] = [
    MemoryFixture(
        key="active_editor",
        content="PR170 eval active current preference: favorite editor is Zed.",
        tags=["state", "temporal", "editor"],
        importance=0.6,
        memory_type="Preference",
    ),
    MemoryFixture(
        key="expired_editor",
        content="PR170 eval expired stale preference: favorite editor was Vim.",
        tags=["state", "temporal", "editor"],
        importance=0.99,
        memory_type="Preference",
        t_invalid_offset_days=-1,
    ),
    MemoryFixture(
        key="future_editor",
        content="PR170 eval future preference: favorite editor will be Nova.",
        tags=["state", "temporal", "editor"],
        importance=0.98,
        memory_type="Preference",
        t_valid_offset_days=1,
    ),
    MemoryFixture(
        key="legacy_tracker",
        content="PR170 eval legacy tracker: project tracker was Jira.",
        tags=["state", "supersession", "tracker"],
        importance=0.99,
    ),
    MemoryFixture(
        key="current_tracker",
        content="PR170 eval current tracker: project tracker is Linear.",
        tags=["state", "supersession", "tracker"],
        importance=0.2,
    ),
    MemoryFixture(
        key="old_deploy",
        content="PR170 eval old deploy target: deploy target was Heroku.",
        tags=["state", "evolution", "deploy"],
        importance=0.99,
    ),
    MemoryFixture(
        key="current_deploy",
        content="PR170 eval current deploy target: deploy target is Railway.",
        tags=["state", "evolution", "deploy"],
        importance=0.2,
    ),
    MemoryFixture(
        key="gated_old_plan",
        content="PR170 eval gated legacy billing plan: plan was Basic.",
        tags=["state", "gated-old"],
        importance=0.99,
    ),
    MemoryFixture(
        key="gated_current_plan",
        content="PR170 eval gated current billing plan: plan is Pro.",
        tags=["state", "replacement-only"],
        importance=0.2,
    ),
    MemoryFixture(
        key="budget_source",
        content="PR170 eval contradiction source: lunch budget is 100 dollars.",
        tags=["state", "contradiction", "budget"],
        importance=0.9,
    ),
    MemoryFixture(
        key="budget_counterpoint",
        content="PR170 eval contradiction counterpoint: lunch budget is 200 dollars.",
        tags=["state", "contradiction", "budget"],
        importance=0.2,
    ),
]

RELATIONS: list[RelationFixture] = [
    RelationFixture("legacy_tracker", "current_tracker", "INVALIDATED_BY"),
    RelationFixture("old_deploy", "current_deploy", "EVOLVED_INTO"),
    RelationFixture("gated_old_plan", "gated_current_plan", "INVALIDATED_BY"),
    RelationFixture("budget_source", "budget_counterpoint", "CONTRADICTS"),
]

PROBES: list[Probe] = [
    Probe(
        id="temporal-validity",
        query="PR170 eval favorite editor",
        params={"tags": ["RUN_TAG", "temporal"], "tag_mode": "all", "limit": 10},
        current_present=["active_editor"],
        current_absent=["expired_editor", "future_editor"],
        unfiltered_present=["active_editor", "expired_editor", "future_editor"],
        min_suppressed_current=2,
    ),
    Probe(
        id="invalidated-replacement",
        query="PR170 eval project tracker",
        params={"tags": ["RUN_TAG", "supersession"], "tag_mode": "all", "limit": 10},
        current_present=["current_tracker"],
        current_absent=["legacy_tracker"],
        unfiltered_present=["legacy_tracker", "current_tracker"],
        min_suppressed_current=1,
    ),
    Probe(
        id="evolved-replacement",
        query="PR170 eval deploy target",
        params={"tags": ["RUN_TAG", "evolution"], "tag_mode": "all", "limit": 10},
        current_present=["current_deploy"],
        current_absent=["old_deploy"],
        unfiltered_present=["old_deploy", "current_deploy"],
        min_suppressed_current=1,
    ),
    Probe(
        id="replacement-respects-tag-filter",
        query="PR170 eval billing plan",
        params={"tags": ["RUN_TAG", "gated-old"], "tag_mode": "all", "limit": 10},
        current_present=[],
        current_absent=["gated_old_plan", "gated_current_plan"],
        unfiltered_present=["gated_old_plan"],
        min_suppressed_current=1,
    ),
    Probe(
        id="contradiction-not-suppressed",
        query="PR170 eval lunch budget",
        params={"tags": ["RUN_TAG", "contradiction"], "tag_mode": "all", "limit": 10},
        current_present=["budget_source", "budget_counterpoint"],
        current_absent=[],
        unfiltered_present=["budget_source", "budget_counterpoint"],
    ),
    Probe(
        id="history-opt-out",
        query="PR170 eval favorite editor",
        params={
            "tags": ["RUN_TAG", "temporal"],
            "tag_mode": "all",
            "limit": 10,
            "current_only": False,
        },
        current_present=["active_editor"],
        current_absent=[],
        unfiltered_present=["active_editor", "expired_editor", "future_editor"],
        expect_mode="unfiltered",
    ),
]


def _parse_http_endpoint(endpoint: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit(
            f"invalid endpoint; expected absolute http(s) URL: {endpoint}"
        )
    return parsed


def is_local_endpoint(endpoint: str) -> bool:
    parsed = _parse_http_endpoint(endpoint)
    return parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def assert_endpoint_allowed(endpoint: str, allow_non_local: bool) -> None:
    is_local = is_local_endpoint(endpoint)
    if allow_non_local or is_local:
        return
    raise SystemExit(f"refusing non-local endpoint without --allow-non-local: {endpoint}")


def _iso_offset(base: dt.datetime, offset_days: int | None) -> str | None:
    if offset_days is None:
        return None
    return (base + dt.timedelta(days=offset_days)).isoformat()


def _json_request(
    endpoint: str,
    token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
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
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-Api-Key": token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        if not raw:
            return {}
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        if not text.strip():
            return {}
        return json.loads(text)


def build_recall_params(
    probe: Probe,
    *,
    run_tag: str,
    current_only: str,
) -> dict[str, Any]:
    params = dict(probe.params)
    params["query"] = probe.query
    params["state_debug"] = True

    tags = params.get("tags")
    if isinstance(tags, list):
        params["tags"] = [run_tag if tag == "RUN_TAG" else tag for tag in tags]

    if "current_only" not in params:
        if current_only == "true":
            params["current_only"] = True
        elif current_only == "false":
            params["current_only"] = False

    return params


def _result_id(result: dict[str, Any]) -> str | None:
    memory = result.get("memory") or {}
    return (
        result.get("id")
        or result.get("memory_id")
        or memory.get("id")
        or memory.get("memory_id")
    )


def _result_content(result: dict[str, Any]) -> str:
    memory = result.get("memory") or {}
    return str(memory.get("content") or result.get("content") or "")


def score_probe(
    probe: Probe,
    response: dict[str, Any],
    memory_ids: dict[str, str],
    *,
    default_expect_mode: str,
) -> dict[str, Any]:
    expect_mode = probe.expect_mode or default_expect_mode
    returned_ids = [_result_id(result) for result in response.get("results", [])]
    returned_set = {memory_id for memory_id in returned_ids if memory_id}

    expected_present_keys = (
        probe.current_present if expect_mode == "current" else probe.unfiltered_present
    )
    expected_absent_keys = probe.current_absent if expect_mode == "current" else []

    missing = [
        key
        for key in expected_present_keys
        if memory_ids.get(key) not in returned_set
    ]
    unexpected = [
        key
        for key in expected_absent_keys
        if memory_ids.get(key) in returned_set
    ]

    state_filter = response.get("state_filter") or {}
    suppressed_count = int(state_filter.get("suppressed_count") or 0)
    suppression_ok = (
        expect_mode != "current"
        or suppressed_count >= probe.min_suppressed_current
    )

    return {
        "id": probe.id,
        "expect_mode": expect_mode,
        "passed": not missing and not unexpected and suppression_ok,
        "missing": missing,
        "unexpected": unexpected,
        "suppressed_count": suppressed_count,
        "expected_min_suppressed": (
            probe.min_suppressed_current if expect_mode == "current" else 0
        ),
        "returned_ids": returned_ids,
        "returned_keys": [
            key for key, memory_id in memory_ids.items() if memory_id in returned_set
        ],
        "top_contents": [
            _result_content(result)[:180] for result in response.get("results", [])[:5]
        ],
    }


def seed_fixtures(
    endpoint: str,
    token: str,
    *,
    run_tag: str,
    now: dt.datetime,
) -> dict[str, str]:
    memory_ids: dict[str, str] = {}
    for fixture in FIXTURES:
        tags = [run_tag, BASE_TAG, *fixture.tags]
        body: dict[str, Any] = {
            "content": fixture.content,
            "tags": tags,
            "importance": fixture.importance,
            "type": fixture.memory_type,
            "confidence": fixture.confidence,
            "metadata": {
                "run_tag": run_tag,
                "fixture_key": fixture.key,
                "eval": BASE_TAG,
            },
        }
        t_valid = _iso_offset(now, fixture.t_valid_offset_days)
        t_invalid = _iso_offset(now, fixture.t_invalid_offset_days)
        if t_valid:
            body["t_valid"] = t_valid
        if t_invalid:
            body["t_invalid"] = t_invalid

        response = _json_request(endpoint, token, "POST", "/memory", body=body)
        memory_id = response.get("memory_id") or response.get("id")
        if not memory_id:
            raise RuntimeError(f"store response missing memory id for fixture {fixture.key}")
        memory_ids[fixture.key] = memory_id

    for relation in RELATIONS:
        _json_request(
            endpoint,
            token,
            "POST",
            "/associate",
            body={
                "memory1_id": memory_ids[relation.source_key],
                "memory2_id": memory_ids[relation.target_key],
                "type": relation.relation_type,
                "strength": relation.strength,
            },
        )

    return memory_ids


def cleanup_run_tag(endpoint: str, token: str, run_tag: str) -> dict[str, Any]:
    snapshot = _json_request(
        endpoint,
        token,
        "GET",
        "/recall",
        params={"tags": [run_tag], "limit": 200, "current_only": False},
        timeout=60,
    )
    ids = []
    for result in snapshot.get("results", []):
        memory_id = _result_id(result)
        if memory_id and memory_id not in ids:
            ids.append(memory_id)

    deleted = 0
    for memory_id in ids:
        _json_request(endpoint, token, "DELETE", f"/memory/{memory_id}", timeout=60)
        deleted += 1

    return {
        "strategy": "per-id",
        "candidate_count": len(ids),
        "deleted_count": deleted,
    }


def run_probes(
    endpoint: str,
    token: str,
    *,
    run_tag: str,
    memory_ids: dict[str, str],
    current_only: str,
    expect_mode: str,
    raw_dir: pathlib.Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for probe in PROBES:
        params = build_recall_params(probe, run_tag=run_tag, current_only=current_only)
        response = _json_request(endpoint, token, "GET", "/recall", params=params)
        (raw_dir / f"{probe.id}.json").write_text(json.dumps(response, indent=2))
        score = score_probe(
            probe,
            response,
            memory_ids,
            default_expect_mode=expect_mode,
        )
        rows.append({"probe": probe, "params": params, "response": response, "score": score})
    return rows


def write_report(
    path: pathlib.Path,
    *,
    label: str,
    endpoint: str,
    run_tag: str,
    current_only: str,
    expect_mode: str,
    memory_ids: dict[str, str],
    rows: list[dict[str, Any]],
    cleanup: dict[str, Any] | None,
) -> None:
    passed = sum(1 for row in rows if row["score"]["passed"])
    lines = [
        f"# Current-state recall eval - {label}",
        "",
        f"- endpoint: `{endpoint}`",
        f"- run_tag: `{run_tag}`",
        f"- current_only: `{current_only}`",
        f"- expectation: `{expect_mode}`",
        f"- probes passed: {passed}/{len(rows)}",
        "",
        "## Memory IDs",
        "",
    ]
    for key, memory_id in sorted(memory_ids.items()):
        lines.append(f"- `{key}`: `{memory_id}`")

    lines.extend(
        [
            "",
            "## Probe Summary",
            "",
            "| Probe | Expect | Status | Missing | Unexpected | Suppressed | Returned keys |",
            "|---|---|---|---|---|---:|---|",
        ]
    )
    for row in rows:
        score = row["score"]
        lines.append(
            "| {probe} | {expect} | {status} | {missing} | {unexpected} | {suppressed} | {returned} |".format(
                probe=score["id"],
                expect=score["expect_mode"],
                status="PASS" if score["passed"] else "FAIL",
                missing=", ".join(score["missing"]) or "-",
                unexpected=", ".join(score["unexpected"]) or "-",
                suppressed=score["suppressed_count"],
                returned=", ".join(score["returned_keys"]) or "-",
            )
        )

    lines.extend(["", "## Top Results", ""])
    for row in rows:
        score = row["score"]
        lines.append(f"### {score['id']}")
        lines.append("")
        lines.append(f"Params: `{json.dumps(row['params'], separators=(',', ':'))}`")
        for index, content in enumerate(score["top_contents"], start=1):
            lines.append(f"{index}. {content}")
        lines.append("")

    if cleanup is not None:
        lines.extend(
            [
                "## Cleanup",
                "",
                f"- deleted_count: {cleanup.get('deleted_count')}",
            ]
        )

    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--label", default=None)
    parser.add_argument(
        "--current-only",
        choices=["default", "true", "false"],
        default="default",
        help="Append a global current_only param to probe calls, or use server default.",
    )
    parser.add_argument(
        "--expect",
        choices=["current", "unfiltered"],
        default="current",
        help="Expected behavior for probes that do not override expectation.",
    )
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--allow-non-local", action="store_true")
    args = parser.parse_args()

    assert_endpoint_allowed(args.endpoint, args.allow_non_local)

    label = args.label or args.expect
    run_tag = args.run_tag or f"{BASE_TAG}-{uuid.uuid4().hex[:10]}"
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        pathlib.Path(args.run_dir)
        if args.run_dir
        else HERE / "data" / "sweep_runs" / f"{timestamp}-current-state-{label}"
    )
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_path = (
        pathlib.Path(args.report)
        if args.report
        else HERE / "data" / "results" / f"{timestamp}-current-state-{label}.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now(dt.timezone.utc)
    cleanup: dict[str, Any] | None = None
    memory_ids: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    try:
        memory_ids = seed_fixtures(args.endpoint, args.token, run_tag=run_tag, now=now)
        (run_dir / "memory-ids.json").write_text(json.dumps(memory_ids, indent=2))
        rows = run_probes(
            args.endpoint,
            args.token,
            run_tag=run_tag,
            memory_ids=memory_ids,
            current_only=args.current_only,
            expect_mode=args.expect,
            raw_dir=raw_dir,
        )
    finally:
        if not args.keep_data:
            try:
                cleanup = cleanup_run_tag(args.endpoint, args.token, run_tag)
            except Exception as exc:  # pragma: no cover - report cleanup failure
                cleanup = {"error": str(exc)}

    summary = {
        "label": label,
        "endpoint": args.endpoint,
        "run_tag": run_tag,
        "current_only": args.current_only,
        "expect": args.expect,
        "memory_ids": memory_ids,
        "rows": [
            {
                "id": row["score"]["id"],
                "params": row["params"],
                "score": row["score"],
            }
            for row in rows
        ],
        "cleanup": cleanup,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    write_report(
        report_path,
        label=label,
        endpoint=args.endpoint,
        run_tag=run_tag,
        current_only=args.current_only,
        expect_mode=args.expect,
        memory_ids=memory_ids,
        rows=rows,
        cleanup=cleanup,
    )

    passed = sum(1 for row in rows if row["score"]["passed"])
    print(f"summary: {run_dir / 'summary.json'}")
    print(f"report: {report_path}")
    print(f"probes: {passed}/{len(rows)} passed")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
