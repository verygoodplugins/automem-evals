"""Hook-replay runner for the AutoMem eval harness.

Pipes canned PostToolUse/Stop fixtures into a variant's hook scripts (verbatim
production code path), drains the resulting memory-queue.jsonl, POSTs each
record to a local AutoMem with an eval-run-<uuid> tag injected, then snapshots
what the run emitted via /recall.

Stdlib-only. Run:

  python3 runners/replay_hooks.py --variant baseline
  python3 runners/replay_hooks.py --variant fix-v1-no-session --cleanup

See docs/session_2026-04-28_hook_replay.md for the design rationale.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VARIANTS_DIR = REPO_ROOT / "variants"
DEFAULT_FIXTURES_DIR = REPO_ROOT / "data" / "hook_fixtures"
DEFAULT_RESULTS_DIR = REPO_ROOT / "data" / "results" / "hook-replay"
DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Pure-logic helpers (unit-tested in test_replay_hooks.py)
# ---------------------------------------------------------------------------


def resolve_variant(name: str, variants_dir: Path = DEFAULT_VARIANTS_DIR) -> dict[str, Path]:
    """Walk the extends-chain and return a {relpath: source_path} map.

    Files defined in the named variant override; files only in an ancestor
    are inherited. Returns absolute paths so callers can read/copy them.
    """
    chain: list[Path] = []
    cur = name
    seen: set[str] = set()
    while cur:
        if cur in seen:
            raise ValueError(f"Cycle in variant extends chain: {cur}")
        seen.add(cur)
        vdir = variants_dir / cur
        if not vdir.is_dir():
            raise FileNotFoundError(f"Variant not found: {vdir}")
        manifest_path = vdir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Variant missing manifest.json: {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        chain.append(vdir)
        cur = manifest.get("extends")

    # Walk chain ancestor-first; later (more-specific) entries override.
    resolved: dict[str, Path] = {}
    for vdir in reversed(chain):
        for path in vdir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(vdir).as_posix()
            if rel == "manifest.json":
                continue
            resolved[rel] = path
    return resolved


def matchers_for_tool(
    settings: dict, tool_name: str | None, hook_kind: str
) -> list[dict[str, str]]:
    """Return the list of {type, command} hook entries that should fire.

    For PostToolUse: filter by `matcher == tool_name` (Claude Code's substring
    semantics, simplified to equality — we only ship "Bash" and "Edit"-style
    matchers in the variants).

    For Stop: matcher is "*"; return only commands that invoke an actual
    hook script (path contains '/hooks/' and ends in '.sh'). Skip
    queue-cleanup.sh and npx-queue-flush invocations — those are the
    flush mechanism the runner replaces (per session doc decision #4).
    """
    out: list[dict[str, str]] = []
    for matcher in settings.get("hooks", {}).get(hook_kind, []):
        m = matcher.get("matcher", "*")
        if hook_kind == "PostToolUse":
            if m != tool_name:
                continue
        elif hook_kind == "Stop":
            pass  # wildcard
        for hook in matcher.get("hooks", []):
            if hook.get("type") != "command":
                continue
            cmd = hook.get("command", "")
            if hook_kind == "Stop":
                # Only fire hooks that invoke a script under a hooks/ dir.
                # Skip queue-cleanup.sh (under scripts/) and npx queue flush —
                # those are the flush mechanism the runner replaces.
                if "hooks/" not in cmd or ".sh" not in cmd:
                    continue
            out.append(hook)
    return out


def inject_eval_run_id(record: dict, eval_run_id: str) -> dict:
    """Return a copy of `record` with eval-run-<id> appended to tags
    and metadata.eval_run_id set. Does not mutate the input.
    """
    out = json.loads(json.dumps(record))  # deep copy via JSON roundtrip
    tags = list(out.get("tags") or [])
    tags.append(f"eval-run-{eval_run_id}")
    out["tags"] = tags
    md = dict(out.get("metadata") or {})
    md["eval_run_id"] = eval_run_id
    out["metadata"] = md
    return out


# ---------------------------------------------------------------------------
# HTTP helpers (validated by smoke run, not unit tests)
# ---------------------------------------------------------------------------


def _http_request(method: str, endpoint: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    parsed = urllib.parse.urlparse(endpoint)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=15)
    headers = {"Content-Type": "application/json", "X-Api-Key": token}
    payload = json.dumps(body) if body is not None else None
    try:
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", errors="replace")
        try:
            parsed_body = json.loads(data) if data else {}
        except json.JSONDecodeError:
            parsed_body = {"_raw": data}
        return resp.status, parsed_body
    finally:
        conn.close()


def health_check(endpoint: str, token: str) -> dict:
    try:
        status, body = _http_request("GET", endpoint, "/health", token)
    except (ConnectionRefusedError, OSError) as e:
        raise SystemExit(
            f"AutoMem unreachable at {endpoint} ({e.__class__.__name__}: {e}). "
            f"Did you 'docker compose up -d' in ../automem? Aborting before any hooks fire."
        ) from None
    if status != 200 or body.get("status") != "healthy":
        raise SystemExit(
            f"AutoMem unhealthy at {endpoint} (status={status}, body={body!r}). "
            f"Did you 'docker compose up -d' in ../automem?"
        )
    return body


def post_memory(record: dict, endpoint: str, token: str) -> tuple[int, dict]:
    return _http_request("POST", endpoint, "/memory", token, body=record)


def recall_by_tag(tag: str, endpoint: str, token: str, limit: int = 200) -> list[dict]:
    """GET /recall?tags=<tag>&limit=<n>. AutoMem returns {results: [{id, memory: {...}, score, ...}, ...]}."""
    qs = urllib.parse.urlencode([("tags", tag), ("limit", str(limit))])
    status, resp = _http_request("GET", endpoint, f"/recall?{qs}", token)
    if status != 200:
        return []
    return resp.get("results") or []


def cleanup_by_tag(tag: str, endpoint: str, token: str) -> dict:
    """Delete every memory tagged eval-run-<id>. /memory/by-tag isn't supported
    so we always do per-id DELETEs against the recall snapshot.
    """
    results = recall_by_tag(tag, endpoint, token, limit=500)
    deleted = 0
    for mem in results:
        mid = mem.get("id") or mem.get("memory_id") or (mem.get("memory") or {}).get("memory_id")
        if not mid:
            continue
        s, _ = _http_request("DELETE", endpoint, f"/memory/{mid}", token)
        if 200 <= s < 300:
            deleted += 1
    return {"strategy": "per-id", "deleted": deleted, "of": len(results)}


# ---------------------------------------------------------------------------
# Variant materialization + synthetic git dirs
# ---------------------------------------------------------------------------


def materialize_variant(resolved: dict[str, Path], sandbox_home: Path) -> dict:
    """Lay out the variant's files inside <sandbox_home>/.claude/ so that the
    hooks' $HOME-relative path lookups resolve correctly.
    """
    base = sandbox_home / ".claude"
    for relpath, src in resolved.items():
        dest = base / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if dest.suffix == ".sh" or dest.suffix == ".py":
            dest.chmod(0o755)
    settings_path = base / "settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(f"Variant has no settings.json after materialization: {settings_path}")
    return json.loads(settings_path.read_text())


def make_synthetic_git_significant(root: Path) -> Path:
    """Create a git repo with 6 commits + multiple file changes that should
    score ≥12 in process-session-memory.py.
    """
    repo = root / "git_significant"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=feat/significant-changes")
    _git(repo, "config", "user.email", "fixture@example.com")
    _git(repo, "config", "user.name", "Fixture")
    # 6 commits, varied file types, sizable diffs (>1000 chars total).
    files = [
        ("src/server.py", "def serve(): return 'ok'\n" * 30, "feat: scaffold server"),
        ("src/auth.py", "def auth(token): return bool(token)\n" * 20, "feat: add auth check"),
        ("src/db.py", "import sqlite3\n# placeholder\n" * 25, "feat: db wiring"),
        ("README.md", "# Project\n\nThis is a sample project.\n" * 15, "docs: README"),
        ("tests/test_server.py", "def test_serve(): assert serve() == 'ok'\n" * 20, "test: basic suite"),
        ("Makefile", "all:\n\techo build\n" * 5, "build: Makefile"),
    ]
    for path, content, msg in files:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        _git(repo, "add", path)
        _git(repo, "commit", "-m", msg, "--quiet")
    # Add some unstaged edits so git status --porcelain returns non-empty
    (repo / "src" / "server.py").write_text("# touched\n" + (repo / "src" / "server.py").read_text())
    (repo / "WIP.md").write_text("scratch\n")
    return repo


def make_synthetic_git_trivial(root: Path) -> Path:
    """Create an empty initialized git repo — should score <12."""
    repo = root / "git_trivial"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.email", "fixture@example.com")
    _git(repo, "config", "user.name", "Fixture")
    return repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Hook execution
# ---------------------------------------------------------------------------


def run_hook(command: str, sandbox_home: Path, fixture_stdin: dict, cwd: Path) -> tuple[int, str, str]:
    """Invoke the hook command via bash -c with HOME overridden to the sandbox.

    The hook command from settings.json may itself be a `bash -c '...'` wrap;
    invoking it through `bash -c <command>` is therefore an extra layer but
    is fine — bash handles nested quoting.
    """
    env = {
        "HOME": str(sandbox_home),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "USER": os.environ.get("USER", "fixture"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    proc = subprocess.run(
        ["bash", "-c", command],
        input=json.dumps(fixture_stdin),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd),
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def fire_fixtures(
    fixtures: list[dict],
    settings: dict,
    sandbox_home: Path,
    git_significant: Path | None,
    git_trivial: Path | None,
) -> tuple[list[dict], list[dict]]:
    """Fire each fixture in order. After all fire, read the queue file and
    return (records, hook_failures). hook_failures captures every non-zero
    hook exit so callers can fail closed — silently dropping a hook would
    let a broken variant masquerade as an improvement (fewer bad records,
    apparent win).

    A fixture with `expected.expects_hook_failure: true` is allowed to
    have its hooks exit non-zero without polluting hook_failures.
    """
    queue_path = sandbox_home / ".claude" / "scripts" / "memory-queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text("")  # truncate

    fixture_log: list[dict] = []
    hook_failures: list[dict] = []
    for fx in fixtures:
        fid = fx["id"]
        kind = fx["kind"]
        stdin_payload = fx.get("stdin", {})
        expects_failure = bool(fx.get("expected", {}).get("expects_hook_failure"))

        if kind == "PostToolUse":
            tool_name = fx.get("tool_name")
            cwd = Path(stdin_payload.get("cwd", str(REPO_ROOT)))
            if not cwd.is_dir():
                cwd = REPO_ROOT
            hooks_to_fire = matchers_for_tool(settings, tool_name, "PostToolUse")
        elif kind == "Stop":
            sentinel = fx.get("cwd_sentinel", "git_significant")
            cwd = git_significant if sentinel == "git_significant" else git_trivial
            if cwd is None:
                print(f"[WARN] {fid}: synthetic git dir not provisioned, skipping", file=sys.stderr)
                continue
            hooks_to_fire = matchers_for_tool(settings, None, "Stop")
        else:
            print(f"[WARN] {fid}: unknown kind {kind!r}, skipping", file=sys.stderr)
            continue

        if not hooks_to_fire:
            print(f"  {fid}: no matchers fired (expected={len(fx.get('expected', {}).get('matchers_should_fire', []))})", file=sys.stderr)
            fixture_log.append({"id": fid, "hooks_fired": 0})
            continue

        for hook in hooks_to_fire:
            rc, out, err = run_hook(hook["command"], sandbox_home, stdin_payload, cwd)
            if rc != 0:
                print(f"  {fid}: hook exited {rc}: {err.strip()[:200]}", file=sys.stderr)
                if not expects_failure:
                    hook_failures.append({
                        "fixture_id": fid,
                        "hook_command": (hook.get("command") or "")[:200],
                        "returncode": rc,
                        "stderr_excerpt": (err or "").strip()[:500],
                        "stdout_excerpt": (out or "").strip()[:500],
                    })

        fixture_log.append({"id": fid, "hooks_fired": len(hooks_to_fire)})

    # Drain queue
    records: list[dict] = []
    if queue_path.exists():
        for line in queue_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] queue line failed JSON parse: {e}: {line[:120]}", file=sys.stderr)
                hook_failures.append({
                    "fixture_id": "<queue-drain>",
                    "hook_command": "<json-decode>",
                    "returncode": -1,
                    "stderr_excerpt": f"{e}: {line[:120]}",
                    "stdout_excerpt": "",
                })
    print(f"  fired {sum(f['hooks_fired'] for f in fixture_log)} hook(s); drained {len(records)} record(s) from queue; {len(hook_failures)} hook failure(s)", file=sys.stderr)
    return records, hook_failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Hook-replay runner for AutoMem eval harness")
    p.add_argument("--variant", required=True, help="Variant name under variants/")
    p.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    p.add_argument("--variants-dir", type=Path, default=DEFAULT_VARIANTS_DIR)
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--token", default=DEFAULT_TOKEN)
    p.add_argument("--cleanup", action="store_true", help="Delete eval-run-<uuid>-tagged memories after snapshot")
    p.add_argument("--keep-sandbox", action="store_true", help="Don't rm -rf the per-run sandbox dir on exit")
    args = p.parse_args(argv)

    args.results_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] health check: {args.endpoint}/health", file=sys.stderr)
    health = health_check(args.endpoint, args.token)
    print(f"      ok — falkordb={health.get('falkordb')}, qdrant={health.get('qdrant')}, memories={health.get('memory_count')}", file=sys.stderr)

    print(f"[2/7] resolve variant: {args.variant}", file=sys.stderr)
    resolved = resolve_variant(args.variant, variants_dir=args.variants_dir)
    print(f"      {len(resolved)} files resolved", file=sys.stderr)

    eval_run_id = uuid.uuid4().hex[:12]
    print(f"[3/7] eval_run_id = {eval_run_id}", file=sys.stderr)

    sandbox = Path(tempfile.mkdtemp(prefix=f"eval-{eval_run_id}-"))
    try:
        print(f"[4/7] materialize variant -> {sandbox}/.claude/", file=sys.stderr)
        settings = materialize_variant(resolved, sandbox)

        # Load fixtures
        fixture_files = sorted(args.fixtures_dir.glob("*.json"))
        fixtures = [json.loads(f.read_text()) for f in fixture_files]
        needs_significant = any(fx.get("cwd_sentinel") == "git_significant" for fx in fixtures)
        needs_trivial = any(fx.get("cwd_sentinel") == "git_trivial" for fx in fixtures)
        sig_dir = make_synthetic_git_significant(sandbox) if needs_significant else None
        triv_dir = make_synthetic_git_trivial(sandbox) if needs_trivial else None

        print(f"[5/7] fire {len(fixtures)} fixtures", file=sys.stderr)
        records, hook_failures = fire_fixtures(fixtures, settings, sandbox, sig_dir, triv_dir)

        print(f"[6/7] POST {len(records)} records to {args.endpoint}/memory with eval-run-{eval_run_id} tag", file=sys.stderr)
        post_results: list[dict] = []
        post_failures: list[dict] = []
        for rec in records:
            tagged = inject_eval_run_id(rec, eval_run_id)
            status, body = post_memory(tagged, args.endpoint, args.token)
            post_results.append({"status": status, "memory_id": (body or {}).get("memory_id") or (body or {}).get("id"), "tags": tagged.get("tags")})
            if not (200 <= status < 300):
                post_failures.append({
                    "status": status,
                    "response_body_excerpt": json.dumps(body, default=str)[:500],
                    "content_excerpt": (rec.get("content") or "")[:200],
                    "tags": tagged.get("tags"),
                })
        ok = sum(1 for r in post_results if 200 <= r["status"] < 300)
        print(f"      {ok}/{len(post_results)} POST'd successfully; {len(post_failures)} POST failure(s)", file=sys.stderr)

        # Recall the run for snapshot
        memories = recall_by_tag(f"eval-run-{eval_run_id}", args.endpoint, args.token)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = args.results_dir / f"{ts}-{args.variant}-snapshot.json"
        run_failed = bool(hook_failures or post_failures)
        snapshot_obj = {
            "variant": args.variant,
            "eval_run_id": eval_run_id,
            "endpoint": args.endpoint,
            "fired_fixtures": [fx["id"] for fx in fixtures],
            "queue_records": records,
            "post_results": post_results,
            "recall_memories": memories,
            "hook_failures": hook_failures,
            "post_failures": post_failures,
            "run_failed": run_failed,
            "captured_at": ts,
        }
        snapshot_path.write_text(json.dumps(snapshot_obj, indent=2, default=str))
        print(f"[7/7] snapshot -> {snapshot_path.relative_to(REPO_ROOT)}", file=sys.stderr)

        if args.cleanup:
            cleanup_result = cleanup_by_tag(f"eval-run-{eval_run_id}", args.endpoint, args.token)
            print(f"      cleanup: {cleanup_result}", file=sys.stderr)
    finally:
        if not args.keep_sandbox:
            shutil.rmtree(sandbox, ignore_errors=True)

    if run_failed:
        print(
            f"FAIL: run produced {len(hook_failures)} hook failure(s) and {len(post_failures)} POST failure(s). "
            f"See {snapshot_path.relative_to(REPO_ROOT)} for stderr/response excerpts. "
            f"Failing closed so a broken variant cannot masquerade as an improvement.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
