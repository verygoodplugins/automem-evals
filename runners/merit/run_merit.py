"""Run the public MERIT harness with an isolated AutoMem memory condition.

Usage (after cloning the official source at its pinned revision)::

    python3 runners/merit/run_merit.py --merit-root ../merit-bench \
      --variant supersede-on-write --maturation both -- --model mock --arcs 2

``matured`` is reported but intentionally blocked until AutoMem exposes the
narrative-clock ``reference_time`` consolidation contract required by
``docs/eval/maturation.md``.  The script never labels a cold execution mature.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from automem_adapter import AutoMemMemory

MERIT_REVISION = "293933d96b1d1849e1f20d1bb324def5de9ed33f"


def _revision(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _maturation_report(requested: str) -> dict[str, object]:
    report: dict[str, object] = {"cold": {"status": "ready", "profile": "cold"}}
    if requested in {"matured", "both"}:
        report["matured"] = {
            "status": "blocked",
            "profile": "matured",
            "reason": "AutoMem lacks the required narrative-clock /consolidate reference_time parameter; see docs/eval/maturation.md.",
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merit-root", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://localhost:8001")
    parser.add_argument("--token", default="test-token")
    parser.add_argument("--variant", choices=["plain", "supersede-on-write"], required=True)
    parser.add_argument("--maturation", choices=["cold", "matured", "both"], default="both")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("data/results/merit"))
    parser.add_argument("merit_args", nargs=argparse.REMAINDER,
                        help="arguments passed to official scripts/run_pilot.py after --")
    args = parser.parse_args()

    root = args.merit_root.resolve()
    if not (root / "merit" / "memory.py").is_file():
        raise SystemExit(f"not an official MERIT checkout: {root}")
    actual = _revision(root)
    if actual != MERIT_REVISION:
        raise SystemExit(f"MERIT revision mismatch: expected {MERIT_REVISION}, got {actual}")

    report = {
        "upstream": "https://github.com/smshweta/merit-bench",
        "revision": actual,
        "license": "MIT",
        "variant": args.variant,
        "maturation": _maturation_report(args.maturation),
        "not_scored_reason": "This command wires the official harness but has not executed an approved model/judge run.",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / f"{args.variant}-run-plan.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    if args.maturation == "matured":
        raise SystemExit(f"matured execution blocked; wrote honest status to {report_path}")

    # The public runner imports its condition map at module-load time.  Patch it
    # only in this process and preserve the rest of its deterministic pipeline.
    sys.path.insert(0, str(root))
    from merit import memory as merit_memory
    from scripts import run_pilot

    condition_key = "C6"
    merit_memory.CONDITIONS[condition_key] = lambda: AutoMemMemory(
        endpoint=args.endpoint, token=args.token, variant=args.variant,
        allow_remote=args.allow_remote,
    )
    run_pilot.CONDITIONS[condition_key] = merit_memory.CONDITIONS[condition_key]
    forwarded = list(args.merit_args)
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    forwarded.extend(["--conditions", condition_key, "--out", str(args.out / "cold")])
    old_argv = sys.argv
    try:
        sys.argv = ["run_pilot.py", *forwarded]
        run_pilot.main()
    finally:
        sys.argv = old_argv
    print(f"MERIT integration plan: {report_path}")


if __name__ == "__main__":
    main()
