#!/usr/bin/env python3
"""
Sweep classes of auto-store noise from an AutoMem instance.

Loads:
  - scenarios/corpus_sweep_v1.json — declarative filter spec + preserve_queries

For each filter:
  1. Enumerate candidates via GET /memory/by-tag, paginated, seeded on the
     filter's most-specific tag.
  2. Client-side narrow: require all of tags_required_all, match any of
     content_prefix_any, created before `before` (if set).
  3. Hard guard: assert filtered count falls within expected_count_range.
     If not, abort the sweep — the filter has drifted and a human needs to
     look. Better one false stop than a thousand false deletes.
  4. --dry-run (default): report counts + 5 samples per filter, no deletes.
  5. --execute: per-id DELETE /memory/<id>. Per-id (not bulk-by-tag) so each
     deletion is gated by all three validators, matching run_beam.py's
     end-of-run cleanup pattern.

Around the sweep:
  - Capture preserve_queries counts BEFORE; assert no regression AFTER.
  - Write per-filter ID logs to data/sweep_runs/<ts>/<filter_id>.ids.txt
    so the deletes are auditable (and so a follow-up run can confirm the IDs
    are gone).

Usage:
  # Dry-run against local clone (default endpoint http://localhost:8001)
  python3 runners/sweep_corpus.py --scenario corpus_sweep_v1

  # Execute against local clone
  python3 runners/sweep_corpus.py --scenario corpus_sweep_v1 --execute

  # Production sweep
  python3 runners/sweep_corpus.py --scenario corpus_sweep_v1 \
      --endpoint https://automem.example.com --token "$AUTOMEM_TOKEN" --execute

Around the sweep (defense-in-depth, post Codex adversarial review):
  - --execute writes a full-record JSONL backup BEFORE deleting; if the
    backup write fails, no deletes happen and the run aborts with exit 2.
  - preserve_query regressions detected after deletes complete still let
    summary.json be written (so the operator has audit data), but the
    process exits 1 so any chained automation cannot treat the run as
    successful.

Exit codes:
  0 — success (dry-run completed, or --execute completed without regression)
  1 — preserve_query regressed after --execute, or filter count fell
      outside expected_count_range (filter drift)
  2 — pre-conditions, configuration, or HTTP failure (scenario file missing,
      filter id not found, baseline counts couldn't be captured, backup
      couldn't be written, post-sweep counts couldn't be captured, etc.)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
SAMPLE_COUNT = 5
PAGE_SIZE = 200


def _http_get(url: str, token: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, headers={"X-Api-Key": token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _http_delete(url: str, token: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, method="DELETE", headers={"X-Api-Key": token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}


def fetch_by_tag_page(
    endpoint: str, token: str, tag: str, limit: int, offset: int
) -> dict:
    """One page of GET /memory/by-tag. Returns the raw JSON envelope."""
    qs = urllib.parse.urlencode([("tags", tag), ("limit", limit), ("offset", offset)])
    return _http_get(f"{endpoint}/memory/by-tag?{qs}", token)


def enumerate_by_tag(endpoint: str, token: str, tag: str) -> list[dict]:
    """Paginate /memory/by-tag until exhausted. Returns full memory records."""
    out: list[dict] = []
    offset = 0
    while True:
        envelope = fetch_by_tag_page(endpoint, token, tag, PAGE_SIZE, offset)
        memories = envelope.get("memories") or envelope.get("results") or []
        if not memories:
            break
        out.extend(memories)
        if len(memories) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return out


def _parse_iso_utc(value: str) -> dt.datetime | None:
    """Parse an ISO 8601 UTC timestamp ('...Z' or '...+00:00'). Returns None
    on missing/empty/unparseable input — callers fail-closed when this happens
    on a candidate (this tool deletes data; an unparseable timestamp must NOT
    be silently treated as 'old enough to delete').
    """
    if not value:
        return None
    try:
        # datetime.fromisoformat does not accept 'Z' before 3.11; normalize.
        normalized = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None


def _get_path(data: dict, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _value_matches(actual, expected) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _metadata_clause_matches(memory: dict, clause: dict) -> bool:
    metadata = memory.get("metadata") or {}
    return all(_value_matches(_get_path(metadata, key), value) for key, value in clause.items())


def matches_filter(memory: dict, filter_spec: dict) -> bool:
    """Apply every configured validator on `filter_spec`.

    Supported keys (each is optional and AND-combined):
    - `tags_required_all`: every listed tag must be present (case-insensitive).
    - `tags_forbidden_any`: candidate is rejected if any listed tag is present.
    - `metadata_required_all`: dotted-path equality (or list-membership) on
      `memory["metadata"]`; every clause must match.
    - `metadata_required_any`: list of metadata clauses; at least one must match.
    - `content_prefix_any`: lstripped content must start with one of the prefixes.
    - `content_regex_any`: lstripped content must match (re.search, MULTILINE)
      one of the patterns. Compiled patterns are cached on `filter_spec` under
      `_compiled_content_regex_any` to avoid recompiling per candidate.
    - `before`: ISO timestamp cutoff. Both the cutoff and the memory's
      `created_at` (or `timestamp`) are parsed as datetimes and the guard
      FAILS CLOSED (returns False) when either is missing or unparseable.
      Earlier raw-string compare treated a missing timestamp as the empty
      string '' — lexicographically less than any ISO timestamp — so a
      missing-`created_at` record would pass and become deletable. With
      actual data on the line, prefer falsely sparing a record over falsely
      deleting one.
    """
    mem_tags = {t.lower() for t in (memory.get("tags") or [])}
    required = {t.lower() for t in filter_spec.get("tags_required_all", [])}
    if not required.issubset(mem_tags):
        return False

    forbidden = {t.lower() for t in filter_spec.get("tags_forbidden_any", [])}
    if forbidden.intersection(mem_tags):
        return False

    metadata_required_all = filter_spec.get("metadata_required_all") or {}
    if metadata_required_all and not _metadata_clause_matches(memory, metadata_required_all):
        return False

    metadata_required_any = filter_spec.get("metadata_required_any") or []
    if metadata_required_any and not any(
        _metadata_clause_matches(memory, clause) for clause in metadata_required_any
    ):
        return False

    prefixes = filter_spec.get("content_prefix_any") or []
    if prefixes:
        content = (memory.get("content") or "").lstrip()
        if not any(content.startswith(p) for p in prefixes):
            return False

    regexes = filter_spec.get("content_regex_any") or []
    if regexes:
        compiled = filter_spec.get("_compiled_content_regex_any")
        if compiled is None or len(compiled) != len(regexes):
            compiled = [re.compile(pattern, flags=re.MULTILINE) for pattern in regexes]
            filter_spec["_compiled_content_regex_any"] = compiled
        content = (memory.get("content") or "").lstrip()
        if not any(regex.search(content) for regex in compiled):
            return False

    before = filter_spec.get("before")
    if before:
        before_dt = _parse_iso_utc(before)
        if before_dt is None:
            # Configured cutoff is unparseable — that's a config error, not a
            # per-memory issue. Fail-closed so a typo in the scenario doesn't
            # delete everything.
            return False
        ts_dt = _parse_iso_utc(memory.get("created_at") or memory.get("timestamp") or "")
        if ts_dt is None:
            return False
        if ts_dt >= before_dt:
            return False

    return True


def baseline_preserve_counts(
    endpoint: str, token: str, preserve_queries: list[dict]
) -> dict[str, int]:
    """For each preserve_query, count memories under those tags."""
    out: dict[str, int] = {}
    for q in preserve_queries:
        # Use enumerate_by_tag for an authoritative count — /recall caps results.
        # If multiple tags are listed, count by EACH (any-of), then dedupe.
        ids: set[str] = set()
        for tag in q["tags"]:
            for m in enumerate_by_tag(endpoint, token, tag):
                mid = m.get("id")
                if mid:
                    ids.add(mid)
        out[q["name"]] = len(ids)
    return out


def assert_no_regression(
    before: dict[str, int],
    after: dict[str, int],
    preserve_queries: list[dict],
) -> list[str]:
    """Return a list of regression messages; empty if all OK."""
    problems: list[str] = []
    for q in preserve_queries:
        b = before.get(q["name"], 0)
        a = after.get(q["name"], 0)
        if a < b:
            problems.append(
                f"{q['name']}: count dropped {b} -> {a} (delta {a - b})"
            )
        if a < q.get("min_results", 0):
            problems.append(
                f"{q['name']}: count {a} below min_results {q['min_results']}"
            )
    return problems


def write_id_log(report_dir: pathlib.Path, filter_id: str, memories: list[dict]) -> pathlib.Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{filter_id}.ids.txt"
    with path.open("w") as f:
        for m in memories:
            mid = m.get("id") or ""
            ts = m.get("created_at") or m.get("timestamp") or ""
            content_head = (m.get("content") or "").replace("\n", " ")[:80]
            f.write(f"{mid}\t{ts}\t{content_head}\n")
    return path


def write_full_backup(report_dir: pathlib.Path, filter_id: str, memories: list[dict]) -> pathlib.Path:
    """Persist the full candidate records (one JSON object per line) BEFORE
    --execute deletion. The .ids.txt log only stores id + 80-char content
    prefix, which is insufficient to restore tags, metadata, or temporal
    fields if the broad validators drift or a filter catches a real memory.

    The caller MUST treat any exception from this function as a hard abort —
    deleting without a restorable record is the failure mode this guards.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{filter_id}.backup.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for m in memories:
            f.write(json.dumps(m, ensure_ascii=False, default=str) + "\n")
    return path


def execute_filter(
    endpoint: str,
    token: str,
    filter_spec: dict,
    candidates: list[dict],
) -> tuple[int, list[str]]:
    """Per-id delete. Returns (deleted_count, error_messages)."""
    errors: list[str] = []
    deleted = 0
    for m in candidates:
        mid = m.get("id")
        if not mid:
            continue
        try:
            _http_delete(f"{endpoint}/memory/{mid}", token)
            deleted += 1
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Already gone — count as success (idempotent).
                deleted += 1
            else:
                errors.append(f"{mid}: HTTP {e.code} {e.reason}")
        except Exception as e:
            errors.append(f"{mid}: {e}")
        # Small breather — don't hammer the API.
        if deleted % 50 == 0 and deleted > 0:
            time.sleep(0.1)
    return deleted, errors


def format_sample(memory: dict) -> str:
    mid = memory.get("id") or "?"
    ts = memory.get("created_at") or memory.get("timestamp") or "?"
    tags = ", ".join((memory.get("tags") or [])[:5])
    content = (memory.get("content") or "").replace("\n", " ")[:90]
    return f"  - {mid} | {ts} | tags=[{tags}] | {content}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--scenario", default="corpus_sweep_v1")
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is dry-run).",
    )
    ap.add_argument(
        "--filter-id",
        default=None,
        help="Run only the named filter (default: all in scenario).",
    )
    ap.add_argument(
        "--report-dir",
        default=None,
        help="Override the report dir (default: data/sweep_runs/<timestamp>/).",
    )
    args = ap.parse_args()

    scenario_path = HERE / "scenarios" / f"{args.scenario}.json"
    if not scenario_path.exists():
        print(f"scenario not found: {scenario_path}", file=sys.stderr)
        return 2
    scenario = json.loads(scenario_path.read_text())

    filters = scenario.get("filters") or []
    if args.filter_id:
        filters = [f for f in filters if f["id"] == args.filter_id]
        if not filters:
            print(f"no filter matched id: {args.filter_id}", file=sys.stderr)
            return 2

    preserve = scenario.get("preserve_queries") or []

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = pathlib.Path(args.report_dir) if args.report_dir else (
        HERE / "data" / "sweep_runs" / ts
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== sweep_corpus {mode} ===")
    print(f"scenario:    {scenario_path.relative_to(HERE)}")
    print(f"endpoint:    {args.endpoint}")
    print(f"filters:     {len(filters)}")
    print(f"report dir:  {report_dir.relative_to(HERE)}")
    print()

    # 1. Baseline preserve counts.
    print("baseline preserve counts:")
    try:
        before = baseline_preserve_counts(args.endpoint, args.token, preserve)
    except Exception as e:
        print(f"failed to capture baselines: {e}", file=sys.stderr)
        return 2
    for q in preserve:
        print(f"  {q['name']}: {before.get(q['name'], 0)}")
    print()

    # 2. Per filter: enumerate + validate + (execute).
    summary: list[dict] = []
    for spec in filters:
        fid = spec["id"]
        seed_tag = spec.get("seed_tag") or spec["tags_required_all"][0]
        print(f"--- {fid} ---")
        print(f"  seed_tag={seed_tag} required={spec['tags_required_all']}")
        try:
            raw = enumerate_by_tag(args.endpoint, args.token, seed_tag)
        except Exception as e:
            print(f"  enumeration failed: {e}", file=sys.stderr)
            return 2
        print(f"  enumerated {len(raw)} memories under seed tag")

        candidates = [m for m in raw if matches_filter(m, spec)]
        print(f"  passed all validators: {len(candidates)}")

        lo, hi = spec.get("expected_count_range", [0, 10**9])
        if not (lo <= len(candidates) <= hi):
            print(
                f"  ABORT: matched count {len(candidates)} is outside "
                f"expected range [{lo}, {hi}].\n"
                f"  Filter has drifted — review samples below and tighten the "
                f"filter before re-running.",
                file=sys.stderr,
            )
            for m in candidates[:SAMPLE_COUNT]:
                print(format_sample(m), file=sys.stderr)
            return 1

        log_path = write_id_log(report_dir, fid, candidates)
        print(f"  id log: {log_path.relative_to(HERE)}")

        # Show samples — first, last, and a couple from the middle.
        if candidates:
            print(f"  samples ({min(SAMPLE_COUNT, len(candidates))}):")
            for m in candidates[:SAMPLE_COUNT]:
                print(format_sample(m))

        if args.execute and candidates:
            # Hard guard: persist full records BEFORE deletion. If we can't
            # write the backup, abort — deleting without a restorable record
            # is precisely the failure mode this protects against.
            try:
                backup_path = write_full_backup(report_dir, fid, candidates)
                print(f"  backup:  {backup_path.relative_to(HERE)} ({len(candidates)} records)")
            except Exception as e:
                print(
                    f"  ABORT: failed to write pre-delete backup for {fid}: {e}\n"
                    f"  No deletes were performed for this filter.",
                    file=sys.stderr,
                )
                return 2

            print(f"  deleting {len(candidates)}…")
            deleted, errors = execute_filter(
                args.endpoint, args.token, spec, candidates
            )
            print(f"  deleted: {deleted} (errors: {len(errors)})")
            for err in errors[:5]:
                print(f"    ! {err}")
            summary.append(
                {"id": fid, "matched": len(candidates), "deleted": deleted, "errors": len(errors), "backup": str(backup_path.relative_to(HERE))}
            )
        else:
            summary.append(
                {"id": fid, "matched": len(candidates), "deleted": 0, "errors": 0}
            )
        print()

    # 3. Post-sweep preserve counts (only meaningful if --execute).
    after: dict[str, int] = {}
    preserve_regressions: list[str] = []
    if args.execute:
        print("post-sweep preserve counts:")
        try:
            after = baseline_preserve_counts(args.endpoint, args.token, preserve)
        except Exception as e:
            print(f"failed to capture post-sweep counts: {e}", file=sys.stderr)
            return 2
        for q in preserve:
            b = before.get(q["name"], 0)
            a = after.get(q["name"], 0)
            delta = a - b
            arrow = "↘" if delta < 0 else ("↗" if delta > 0 else "·")
            print(f"  {q['name']}: {b} -> {a} {arrow}")
        print()

        preserve_regressions = assert_no_regression(before, after, preserve)
        if preserve_regressions:
            print("REGRESSION DETECTED in preserve_queries:", file=sys.stderr)
            for p in preserve_regressions:
                print(f"  ! {p}", file=sys.stderr)
            print(
                "Sweep deletions were applied but some preserve counts dropped.\n"
                "Investigate before running this filter set again.",
                file=sys.stderr,
            )

    # 4. Write summary JSON. Always write before exiting so the report is
    # available for diagnosis even when the sweep regressed.
    summary_payload = {
        "timestamp": ts,
        "endpoint": args.endpoint,
        "scenario": str(scenario_path.relative_to(HERE)),
        "mode": mode,
        "filters": summary,
        "preserve_before": before,
        "preserve_after": after,
        "preserve_regressions": preserve_regressions,
    }
    (report_dir / "summary.json").write_text(json.dumps(summary_payload, indent=2))
    print(f"summary: {(report_dir / 'summary.json').relative_to(HERE)}")

    if not args.execute:
        print(
            "\nThis was a DRY-RUN. Review the samples and id logs above, then "
            "rerun with --execute to perform deletions."
        )

    # Fail closed at the end. The deletes already happened — that's exactly why
    # the caller needs a non-zero exit: any downstream automation must NOT
    # treat this run as successful and chain further destructive operations
    # off it. summary.json contains preserve_regressions[] for programmatic
    # parsing.
    if preserve_regressions:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
