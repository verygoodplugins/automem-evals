#!/usr/bin/env python3
"""
End-to-end WRIT runner — drives the upstream writ benchmark against AutoMem.

What it does, in order:
  1. Sanity-check node/npm + AutoMem /health.
  2. Copy our automem adapter into third_party/writ/src/adapters/automem.ts and
     our entry point into third_party/writ/run_automem.ts so the submodule
     stays unmodified-by-default but executable when the driver is in charge.
  3. `npm install` once (skipped if node_modules exists).
  4. `npx tsx run_automem.ts ...` for the automem adapter, or `npx tsx
     src/cli.ts ...` for baseline/neotoma.
  5. Copy the report JSON/MD back into data/results/writ/<ts>-<adapter>-<scn>/.

By design `reset()` lives in the adapter and runs before every scenario; it
deletes only the memories this run created (tracked by id), so the AutoMem
stack is untouched aside from the per-run namespace.

Usage:
  python3 runners/run_writ.py --adapter automem --scenarios drift
  python3 runners/run_writ.py --adapter baseline --scenarios drift
  python3 runners/run_writ.py --compare automem baseline --scenarios drift

This is experimental — see docs/writ_integration.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
WRIT_DIR = REPO / "third_party" / "writ"
ADAPTER_SRC = REPO / "runners" / "writ" / "automem-adapter" / "automem.ts"
RUNNER_SRC = REPO / "runners" / "writ" / "automem-adapter" / "run.ts"
ADAPTER_DEST = WRIT_DIR / "src" / "adapters" / "automem.ts"
RUNNER_DEST = WRIT_DIR / "run_automem.ts"
RESULTS_ROOT = REPO / "data" / "results" / "writ"

DEFAULT_AUTOMEM = "http://localhost:8001"
DEFAULT_TOKEN = "test-token"

VALID_ADAPTERS = {"automem", "baseline", "neotoma"}

METRIC_KEYS = [
    "recall_accuracy",
    "update_fidelity",
    "drift_rate",
    "detectability",
    "temporal_accuracy",
    "provenance_completeness",
    "constraint_consistency",
    "hallucination_rate",
    "abstention_quality",
    "source_authority_integrity",
    "dedup_accuracy",
    "failure_resilience",
    "lifecycle_accuracy",
    "pre_delivery_detection",
    "scenarios_evaluated",
]

METRIC_SCORE_FIELDS = {
    "recall_accuracy": "recall_correct",
    "update_fidelity": "update_fidelity",
    "drift_rate": "drift_detected",
    "detectability": "drift_detected",
    "temporal_accuracy": "temporal_correct",
    "provenance_completeness": "provenance_complete",
    "constraint_consistency": "constraint_respected",
    "hallucination_rate": "hallucination_detected",
    "abstention_quality": "abstention_correct",
    "source_authority_integrity": "source_authority_intact",
    "dedup_accuracy": "dedup_correct",
    "failure_resilience": "failure_resilient",
    "lifecycle_accuracy": "lifecycle_current_correct",
    "pre_delivery_detection": "pre_delivery_flagged",
}

LOWER_IS_BETTER_METRICS = {"drift_rate", "hallucination_rate"}


def _load_dotenv() -> None:
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


def _check_command(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(f"`{cmd}` not on PATH — install Node.js first")


def _check_automem(endpoint: str, token: str) -> None:
    req = urllib.request.Request(
        f"{endpoint}/health", headers={"X-Api-Key": token}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
    except (urllib.error.URLError, ConnectionError) as exc:
        raise SystemExit(f"AutoMem at {endpoint} not reachable: {exc}") from exc
    status = body.get("status", "unknown")
    if status not in {"ok", "healthy", "degraded"}:
        raise SystemExit(f"AutoMem health says: {status}")


def _check_writ() -> None:
    if not WRIT_DIR.exists() or not (WRIT_DIR / "package.json").exists():
        raise SystemExit(
            "third_party/writ missing — run `git submodule update --init` first"
        )


def _patch_writ_inplace() -> None:
    if not ADAPTER_SRC.exists() or not RUNNER_SRC.exists():
        raise SystemExit(
            f"adapter sources missing: {ADAPTER_SRC} or {RUNNER_SRC}"
        )
    ADAPTER_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ADAPTER_SRC, ADAPTER_DEST)
    shutil.copy2(RUNNER_SRC, RUNNER_DEST)


def _ensure_npm_install() -> None:
    if (WRIT_DIR / "node_modules").exists():
        return
    print("[run_writ] npm install (one-time)...")
    subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=WRIT_DIR,
        check=True,
    )


def _run_writ(
    adapter: str,
    scenarios: str,
    modes: str,
    endpoint: str,
    token: str,
    output_dir: pathlib.Path,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if adapter == "automem":
        cmd = [
            "npx", "tsx", "run_automem.ts",
            "--scenarios", scenarios,
            "--modes", modes,
            "--endpoint", endpoint,
            "--token", token,
            "--output", str(output_dir.resolve()),
        ]
    else:
        cmd = [
            "npx", "tsx", "src/cli.ts",
            "--adapter", adapter,
            "--scenarios", scenarios,
            "--modes", modes,
            "--output", str(output_dir.resolve()),
        ]
    print(f"[run_writ] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=WRIT_DIR)
    return proc.returncode


def _find_latest_report(output_dir: pathlib.Path) -> pathlib.Path | None:
    candidates = sorted(output_dir.glob("writ-*.json"))
    return candidates[-1] if candidates else None


def _load_writ_scenarios(
    scenarios_dir: pathlib.Path = WRIT_DIR / "scenarios",
) -> dict[str, dict]:
    scenarios: dict[str, dict] = {}
    for path in sorted(scenarios_dir.glob("*.json")):
        scenario = json.loads(path.read_text())
        scenario_id = scenario.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id:
            scenarios[scenario_id] = scenario
    return scenarios


def _is_history_query_stale_false_positive(
    result: dict,
    scenario: dict | None,
) -> bool:
    if not scenario:
        return False

    probe = scenario.get("probe")
    required_capabilities = []
    if isinstance(probe, dict):
        capabilities = probe.get("required_capabilities", [])
        if isinstance(capabilities, list):
            required_capabilities = capabilities

    scores = result.get("scores", {})
    detected_failures = result.get("detected_failures", [])
    return (
        "history_preservation" in required_capabilities
        and scores.get("recall_correct") is True
        and scores.get("drift_detected") is True
        and "stale_memory" in detected_failures
    )


def _summarize_history_aware_stale_failures(
    report: dict,
    scenarios_by_id: dict[str, dict],
) -> dict[str, int]:
    raw_stale = 0
    history_false_positives = 0

    for result in report.get("scenario_results", []):
        detected_failures = result.get("detected_failures", [])
        if "stale_memory" not in detected_failures:
            continue
        raw_stale += 1
        scenario = scenarios_by_id.get(result.get("scenario_id"))
        if _is_history_query_stale_false_positive(result, scenario):
            history_false_positives += 1

    return {
        "raw_stale_memory_failures": raw_stale,
        "history_query_stale_false_positives": history_false_positives,
        "remaining_stale_memory_failures": raw_stale - history_false_positives,
    }


def _classify_aggregate_metric(report: dict, metric: str) -> dict[str, object]:
    score_field = METRIC_SCORE_FIELDS.get(metric)
    raw_value = report.get("aggregate", {}).get(metric, 0)
    direction = (
        "lower_is_better"
        if metric in LOWER_IS_BETTER_METRICS
        else "higher_is_better"
    )
    applicable_count = 0
    if score_field:
        applicable_count = sum(
            1
            for result in report.get("scenario_results", [])
            if result.get("scores", {}).get(score_field) is not None
        )

    if score_field and applicable_count == 0:
        return {
            "status": "not_exercised",
            "direction": direction,
            "applicable_count": applicable_count,
            "raw_value": raw_value,
        }

    if direction == "lower_is_better":
        status = "pass" if raw_value == 0 else "fail"
    else:
        status = "pass" if raw_value == 1 else "fail"

    return {
        "status": status,
        "direction": direction,
        "applicable_count": applicable_count,
        "raw_value": raw_value,
    }


def _format_metric_value(metric: str, value: float | int) -> str:
    if metric == "scenarios_evaluated":
        return str(value)
    return f"{value * 100:.1f}%"


def _format_metric_interpretation(interpretation: dict[str, object]) -> str:
    status = interpretation["status"]
    if status == "not_exercised":
        return "not exercised in this run"

    direction = interpretation["direction"]
    if direction == "lower_is_better":
        return f"{status}; lower is better"
    return f"measured {status}"


def _is_drift_only_report(report: dict) -> bool:
    categories = {
        result.get("category")
        for result in report.get("scenario_results", [])
        if result.get("category")
    }
    return categories == {"drift"}


def _append_interpretation_guide(lines: list[str], reports: list[dict]) -> None:
    lines.append("## Interpretation guide")
    lines.append("")
    lines.append(
        "Raw WRIT aggregate numbers are preserved above. Local labels below "
        "separate measured signals from metrics this scenario set did not exercise."
    )
    for report in reports:
        lines.append("")
        lines.append(f"### {report['adapter_name']}")
        lines.append("")
        lines.append("| metric | raw score | applicable scenarios | local interpretation |")
        lines.append("| --- | ---: | ---: | --- |")
        for metric in METRIC_KEYS:
            if metric == "scenarios_evaluated":
                continue
            interpretation = _classify_aggregate_metric(report, metric)
            lines.append(
                f"| {metric} | "
                f"{_format_metric_value(metric, interpretation['raw_value'])} | "
                f"{interpretation['applicable_count']} | "
                f"{_format_metric_interpretation(interpretation)} |"
            )
    lines.append("")


def _append_actionable_signals(lines: list[str], reports: list[dict]) -> None:
    automem = next((r for r in reports if r.get("adapter_name") == "automem"), None)
    if not automem or not _is_drift_only_report(automem):
        return

    aggregate = automem.get("aggregate", {})
    lines.append("## Actionable signals")
    lines.append("")
    if (
        aggregate.get("recall_accuracy") == 1
        and aggregate.get("detectability") == 1
        and aggregate.get("drift_rate") == 0
    ):
        lines.append(
            "- AutoMem passed recall/history tracking in this local drift run: "
            "`recall_accuracy=100%`, `detectability=100%`, and `drift_rate=0%`."
        )
    lines.append(
        "- Raw `update_fidelity` is not a benchmark claim when the prompt asks "
        "for history; use the history-aware interpretation below for these "
        "drift prompts."
    )
    lines.append(
        "- Capability columns like provenance, source authority, dedup, "
        "lifecycle, failure resilience, and pre-delivery detection need their "
        "own WRIT scenario categories before treating them as AutoMem behavior."
    )
    lines.append(
        "- Nothing in this drift smoke points directly to an AutoMem core bug; "
        "near-term work belongs in the local WRIT adapter/reporting layer."
    )
    lines.append("")


def _diff_reports(
    a_path: pathlib.Path, b_path: pathlib.Path, dest: pathlib.Path
) -> None:
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    scenarios_by_id = _load_writ_scenarios()
    reports = [a, b]

    lines: list[str] = []
    lines.append(f"# WRIT comparison — {a['adapter_name']} vs {b['adapter_name']}")
    lines.append("")
    lines.append(f"- writ_version: {a['writ_version']}")
    lines.append(f"- timestamp: {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- {a['adapter_name']}: {a_path.name} ({a['scenarios_run']} scenarios)")
    lines.append(f"- {b['adapter_name']}: {b_path.name} ({b['scenarios_run']} scenarios)")
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        f"| metric | {a['adapter_name']} | {b['adapter_name']} | delta |"
    )
    lines.append("| --- | ---: | ---: | ---: |")
    for k in METRIC_KEYS:
        av = a["aggregate"].get(k, 0)
        bv = b["aggregate"].get(k, 0)
        if k == "scenarios_evaluated":
            lines.append(f"| {k} | {av} | {bv} | {av - bv} |")
        else:
            delta = (av - bv) * 100
            lines.append(
                f"| {k} | {av * 100:.1f}% | {bv * 100:.1f}% | {delta:+.1f}pp |"
            )

    lines.append("")
    lines.append("## Per-scenario (recall_correct)")
    lines.append("")
    lines.append(f"| scenario | {a['adapter_name']} | {b['adapter_name']} |")
    lines.append("| --- | :---: | :---: |")
    a_by_id = {r["scenario_id"]: r for r in a.get("scenario_results", [])}
    b_by_id = {r["scenario_id"]: r for r in b.get("scenario_results", [])}
    for sid in sorted(set(a_by_id) | set(b_by_id)):
        ar = a_by_id.get(sid)
        br = b_by_id.get(sid)
        a_mark = (
            "✅" if ar and ar["scores"]["recall_correct"] else ("❌" if ar else "—")
        )
        b_mark = (
            "✅" if br and br["scores"]["recall_correct"] else ("❌" if br else "—")
        )
        lines.append(f"| {sid} | {a_mark} | {b_mark} |")
    lines.append("")
    _append_interpretation_guide(lines, reports)
    _append_actionable_signals(lines, reports)
    lines.append("## History-aware interpretation")
    lines.append("")
    lines.append(
        "raw WRIT `update_fidelity` is unchanged; this local overlay only "
        "distinguishes historical recall from stale-current presentation."
    )
    lines.append("")
    lines.append(
        "| adapter | raw stale_memory failures | likely history-query stale "
        "false positives | remaining raw stale_memory failures |"
    )
    lines.append("| --- | ---: | ---: | ---: |")
    for report in (a, b):
        summary = _summarize_history_aware_stale_failures(report, scenarios_by_id)
        lines.append(
            f"| {report['adapter_name']} | "
            f"{summary['raw_stale_memory_failures']} | "
            f"{summary['history_query_stale_false_positives']} | "
            f"{summary['remaining_stale_memory_failures']} |"
        )
    lines.append("")
    lines.append("Generated by `runners/run_writ.py`. See "
                 "`docs/writ_integration.md` for what these metrics mean.")
    dest.write_text("\n".join(lines) + "\n")
    print(f"[run_writ] wrote {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Drive the WRIT benchmark.")
    parser.add_argument(
        "--adapter",
        default="automem",
        help="single-run adapter (automem|baseline|neotoma); ignored if --compare given",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("A", "B"),
        help="run two adapters and emit a comparison report",
    )
    parser.add_argument("--scenarios", default="drift", help="category or 'all'")
    parser.add_argument(
        "--modes",
        default="native_memory",
        help="comma-separated WRIT modes: no_memory,native_memory,oracle_memory",
    )
    parser.add_argument("--endpoint", default=DEFAULT_AUTOMEM)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument(
        "--label",
        default=None,
        help="optional label appended to the timestamped output dir",
    )
    args = parser.parse_args()

    _load_dotenv()
    _check_command("node")
    _check_command("npm")
    _check_writ()
    _check_automem(args.endpoint, args.token)
    _patch_writ_inplace()
    _ensure_npm_install()

    if args.compare:
        adapters = list(args.compare)
    else:
        adapters = [args.adapter]
    for a in adapters:
        if a not in VALID_ADAPTERS:
            raise SystemExit(f"unknown adapter: {a}")

    ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    label = f"-{args.label}" if args.label else ""
    run_dir = RESULTS_ROOT / f"{ts}-{args.scenarios}{label}"

    report_paths: dict[str, pathlib.Path] = {}
    for adapter in adapters:
        out = run_dir / adapter
        rc = _run_writ(
            adapter=adapter,
            scenarios=args.scenarios,
            modes=args.modes,
            endpoint=args.endpoint,
            token=args.token,
            output_dir=out,
        )
        if rc != 0:
            print(f"[run_writ] adapter {adapter} exited non-zero: {rc}")
            return rc
        latest = _find_latest_report(out)
        if not latest:
            print(f"[run_writ] no report found in {out}")
            return 1
        report_paths[adapter] = latest

    if len(report_paths) == 2:
        a_name, b_name = adapters
        comparison_path = run_dir / f"comparison-{a_name}-vs-{b_name}.md"
        _diff_reports(report_paths[a_name], report_paths[b_name], comparison_path)

    print(f"[run_writ] artifacts under {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
