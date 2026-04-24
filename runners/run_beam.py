#!/usr/bin/env python3
"""
End-to-end BEAM smoke runner — wraps the upstream runner with our shim.

What it does, in order:
  1. Sanity-check OPENAI_API_KEY and AutoMem /health.
  2. Pick a free port, start runners/beam_shim.py pointed at AutoMem.
  3. `python -m benchmarks.beam.run --backend oss --mem0-host http://127.0.0.1:<shim>`
     run from inside third_party/memory-benchmarks so its dataset cache lands
     in the submodule (gitignored upstream).
  4. After the runner exits, stop the shim, copy BEAM's predicted_<project>/
     output into data/results/beam/<ts>-<tier>-<convs>/, and issue a final
     delete-by-tag sweep so we don't leave BEAM memories in AutoMem.

Usage:
  python3 runners/run_beam.py --tier 100K --conversations 0-1

Requires:
  - OPENAI_API_KEY in env
  - upstream deps installed: pip install -r third_party/memory-benchmarks/requirements.txt
  - AutoMem stack up at http://localhost:8001

This is experimental — see data/results/beam/README.md before quoting any
numbers it produces.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from judge_policy import CANONICAL_BENCHMARK_JUDGE_MODEL, DEFAULT_JUDGE_PROVIDER, judge_metadata

REPO = pathlib.Path(__file__).resolve().parent.parent
UPSTREAM = REPO / "third_party" / "memory-benchmarks"
SHIM_V1 = REPO / "runners" / "beam_shim.py"
SHIM_V2 = REPO / "runners" / "beam_shim_v2.py"
RESULTS_ROOT = REPO / "data" / "results" / "beam"
BEAM_VENV_PY = REPO / ".venv-beam" / "bin" / "python"
DEFAULT_AUTOMEM = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"
VALID_CHAT_SIZES = {"100K", "500K", "1M", "10M"}
SHIM_VERSIONS = {"v1", "v2"}
DEFAULT_EXTRACTION_MODEL = "gpt-4o-mini"


def _load_dotenv() -> None:
    """Populate os.environ from REPO/.env for keys not already set.

    Stdlib-only parser — no python-dotenv dependency. Handles KEY=VALUE, #
    comments, blank lines, and surrounding single/double quotes. Existing env
    vars win (so CI or `env OPENAI_API_KEY=... python ...` still overrides)."""
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _beam_python() -> str:
    """Prefer .venv-beam if present (holds upstream BEAM's aiohttp/openai/...
    which PEP 668 won't let us install into Homebrew Python)."""
    if BEAM_VENV_PY.exists():
        return str(BEAM_VENV_PY)
    return sys.executable


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_shim(url: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1.5) as r:
                body = json.loads(r.read())
            if body.get("status") == "ok":
                return
        except (urllib.error.URLError, ConnectionError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(0.2)
    raise SystemExit(f"shim at {url} never became healthy: {last}")


def _preflight(automem_url: str, token: str) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set — BEAM needs it for the answerer and judge LLMs."
        )
    if not UPSTREAM.exists():
        raise SystemExit(
            f"submodule missing: {UPSTREAM} — run `git submodule update --init`"
        )

    try:
        req = urllib.request.Request(
            f"{automem_url}/health", headers={"X-Api-Key": token}
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            body = json.loads(r.read())
    except Exception as exc:
        raise SystemExit(f"AutoMem /health probe failed: {exc}")
    if body.get("status") != "healthy":
        raise SystemExit(f"AutoMem is not healthy: {body}")


def _sweep_run_tag(automem_url: str, token: str, sweep_tag: str) -> int:
    """Delete everything tagged with this run's sweep tag on AutoMem. Paranoia
    against stale per-conversation users that the runner left behind on crash.

    This is scoped to THIS run's tag only — so two concurrent run_beam.py
    processes (each with its own unique tag) won't wipe each other's data."""
    deleted = 0
    hdrs = {"X-Api-Key": token}
    while True:
        params = [("tags", sweep_tag), ("limit", "500"), ("query", "")]
        from urllib.parse import urlencode

        req = urllib.request.Request(
            f"{automem_url}/recall?{urlencode(params)}", headers=hdrs
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        results = resp.get("results") or []
        if not results:
            break
        for r in results:
            mem = r.get("memory") or {}
            mid = mem.get("id") or r.get("id")
            if not mid:
                continue
            dr = urllib.request.Request(
                f"{automem_url}/memory/{mid}", method="DELETE", headers=hdrs
            )
            try:
                with urllib.request.urlopen(dr, timeout=10) as dresp:
                    dresp.read()
                deleted += 1
            except Exception:
                pass
        if len(results) < 500:
            break
    return deleted


def _annotate_result_json(path: pathlib.Path, metadata: dict[str, object]) -> None:
    """Add wrapper-level judge metadata to copied upstream result JSON."""
    try:
        data = json.loads(path.read_text())
        result_metadata = data.setdefault("metadata", {})
        if isinstance(result_metadata, dict):
            result_metadata.update(metadata)
            path.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        print(f"warning: could not annotate {path.name}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run upstream BEAM through the AutoMem shim"
    )
    ap.add_argument(
        "--tier",
        default="100K",
        help=f"chat-sizes value, one of {sorted(VALID_CHAT_SIZES)}",
    )
    ap.add_argument(
        "--conversations",
        default="0-1",
        help="BEAM conversation spec, e.g. 0-1 or 0,1,5",
    )
    ap.add_argument(
        "--project-name", default=None, help="BEAM project name (default: automem-<ts>)"
    )
    ap.add_argument(
        "--answerer-model", default=None, help="Override BEAM answerer model"
    )
    ap.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Override BEAM judge model " f"(default: {CANONICAL_BENCHMARK_JUDGE_MODEL})"
        ),
    )
    ap.add_argument(
        "--judge-profile",
        default=None,
        help=(
            "Metadata label for non-canonical comparison runs, "
            "for example published-mem0-gpt-5."
        ),
    )
    ap.add_argument("--top-k", type=int, default=None, help="Override BEAM --top-k")
    ap.add_argument(
        "--extra", default="", help="Extra args appended to BEAM (space-separated)"
    )
    ap.add_argument("--automem", default=DEFAULT_AUTOMEM)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument(
        "--sweep-tag",
        default=None,
        help=(
            "Override the per-run sweep tag (default: beam-run-<uuid8>). "
            "Replaces the legacy 'beam' tag on every stored memory so "
            "concurrent runs can't cross-delete each other's data."
        ),
    )
    ap.add_argument(
        "--shim-version",
        default="v1",
        choices=sorted(SHIM_VERSIONS),
        help=(
            "v1: raw-dialogue pass-through (original). "
            "v2: calls gpt-4o-mini with mem0's FACT_RETRIEVAL_PROMPT to extract "
            "atomic facts before POST /memory — closer to mem0-OSS's own pipeline."
        ),
    )
    ap.add_argument(
        "--extraction-model",
        default=DEFAULT_EXTRACTION_MODEL,
        help="V2 only: OpenAI model used for fact extraction.",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Print the upstream command and exit"
    )
    args = ap.parse_args()

    if args.tier not in VALID_CHAT_SIZES:
        raise SystemExit(f"--tier must be one of {sorted(VALID_CHAT_SIZES)}")

    _load_dotenv()
    _preflight(args.automem, args.token)

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    conv_slug = args.conversations.replace(",", "_").replace("-", "_")
    shim_suffix = "" if args.shim_version == "v1" else f"-{args.shim_version}"
    run_dir = RESULTS_ROOT / f"{ts}-{args.tier}-{conv_slug}{shim_suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    project_name = args.project_name or f"automem-{ts}"
    sweep_tag = args.sweep_tag or f"beam-run-{uuid.uuid4().hex[:8]}"
    effective_judge_model = args.judge_model or CANONICAL_BENCHMARK_JUDGE_MODEL
    effective_judge_provider = DEFAULT_JUDGE_PROVIDER
    effective_judge_metadata = judge_metadata(
        effective_judge_model,
        provider=effective_judge_provider,
        profile=args.judge_profile,
    )
    shim_port = _find_free_port()
    shim_url = f"http://127.0.0.1:{shim_port}"
    output_dir = run_dir / "beam-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # We invoke runners.beam_patched_main instead of `benchmarks.beam.run`
    # directly — it's a 50-line wrapper that monkey-patches LLMClient's
    # hardcoded 120s timeout before BEAM imports. Local inference on M5 Max
    # needs longer budgets; upstream doesn't expose a CLI override. Pass-through
    # argv is identical.
    cmd = [
        _beam_python(),
        str(REPO / "runners" / "beam_patched_main.py"),
        "--project-name",
        project_name,
        "--backend",
        "oss",
        "--mem0-host",
        shim_url,
        "--chat-sizes",
        args.tier,
        "--conversations",
        args.conversations,
        "--output-dir",
        str(output_dir),
    ]
    if args.answerer_model:
        cmd += ["--answerer-model", args.answerer_model]
    cmd += ["--judge-model", effective_judge_model]
    if args.top_k is not None:
        cmd += ["--top-k", str(args.top_k)]
    if args.extra:
        cmd += args.extra.split()

    shim_note = {
        "v1": "V1 pass-through shim (no LLM fact extraction).",
        "v2": f"V2 extraction shim — gpt-4o-mini using mem0 FACT_RETRIEVAL_PROMPT (pinned at runners/prompts/mem0_prompts_daa4495.py).",
    }[args.shim_version]
    manifest = {
        "timestamp": ts,
        "tier": args.tier,
        "conversations": args.conversations,
        "project_name": project_name,
        "sweep_tag": sweep_tag,
        "shim_version": args.shim_version,
        "extraction_model": (
            args.extraction_model if args.shim_version == "v2" else None
        ),
        **effective_judge_metadata,
        "shim_url": shim_url,
        "automem_url": args.automem,
        "upstream_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True
        ).strip(),
        "command": cmd,
        "notes": f"{shim_note} See data/results/beam/README.md.",
    }
    (run_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print(f"run dir:      {run_dir.relative_to(REPO)}")
    print(f"shim url:     {shim_url}")
    print(
        f"shim version: {args.shim_version}"
        + (f" (extractor={args.extraction_model})" if args.shim_version == "v2" else "")
    )
    print(f"sweep tag:    {sweep_tag}")
    print(f"upstream cmd: {' '.join(cmd)}")

    if args.dry_run:
        return 0

    shim_log = run_dir / "shim.log"
    shim_stats = run_dir / "shim_stats.jsonl" if args.shim_version == "v2" else None
    # V2 shim needs the openai SDK; it lives in .venv-beam. V1 is stdlib-only.
    shim_py = _beam_python() if args.shim_version == "v2" else sys.executable
    shim_path = SHIM_V2 if args.shim_version == "v2" else SHIM_V1
    shim_cmd = [
        shim_py,
        str(shim_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(shim_port),
        "--upstream",
        args.automem,
        "--token",
        args.token,
        "--sweep-tag",
        sweep_tag,
    ]
    if args.shim_version == "v2":
        shim_cmd += ["--extraction-model", args.extraction_model]
        if shim_stats is not None:
            shim_cmd += ["--stats-path", str(shim_stats)]
    shim_proc = subprocess.Popen(
        shim_cmd,
        stdout=shim_log.open("w"),
        stderr=subprocess.STDOUT,
        env={**os.environ},  # pass OPENAI_API_KEY into the subprocess for V2 extraction
    )

    upstream_rc = 1
    try:
        _wait_for_shim(shim_url)
        print(f"shim up — running BEAM (log: {shim_log.relative_to(REPO)})")
        upstream = subprocess.run(cmd, cwd=UPSTREAM)
        upstream_rc = upstream.returncode
        print(f"upstream exit: {upstream_rc}")
    finally:
        if shim_proc.poll() is None:
            shim_proc.send_signal(signal.SIGINT)
            try:
                shim_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                shim_proc.kill()
        swept = _sweep_run_tag(args.automem, args.token, sweep_tag)
        print(f"swept {swept} remaining memories tagged {sweep_tag!r} from AutoMem")

    # Upstream's results live at output_dir/predicted_<project_name>/
    # Leave them in place; MANIFEST.json points to their location.
    predicted = output_dir / f"predicted_{project_name}"
    if predicted.exists():
        print(f"predicted dir: {predicted.relative_to(REPO)}")
        # Convenience: surface the top-level beam_results_*.json if present
        for fp in sorted(output_dir.glob("beam_results_*.json")):
            _annotate_result_json(fp, effective_judge_metadata)
            shutil.copy(fp, run_dir / fp.name)
            print(f"copied: {fp.name}")

    manifest["upstream_rc"] = upstream_rc
    (run_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return upstream_rc


if __name__ == "__main__":
    sys.exit(main())
