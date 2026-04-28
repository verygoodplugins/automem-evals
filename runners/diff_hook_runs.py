"""Render a markdown comparison of two hook-replay metrics JSONs.

Reads two metrics JSON files (one per variant) and emits a markdown report
suitable for a PR description: per-metric tables with deltas and a verdict
section calling out which audit findings the variant change addresses.

Usage:
  python3 runners/diff_hook_runs.py \\
      data/results/hook-replay/<ts>-baseline-snapshot.metrics.json \\
      data/results/hook-replay/<ts>-fix-v1-no-session-snapshot.metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _delta(a: float | int, b: float | int) -> str:
    if a == b:
        return ""
    diff = b - a
    if isinstance(a, int) and isinstance(b, int):
        return f"{diff:+d}"
    return f"{diff:+.3f}"


def _row(label: str, a, b, direction: str = "lower_is_better") -> str:
    """direction: 'lower_is_better' | 'higher_is_better' | 'informational'."""
    delta = _delta(a, b)
    suffix = ""
    if delta and direction != "informational":
        improved = (direction == "lower_is_better" and a > b) or (
            direction == "higher_is_better" and a < b
        )
        regressed = (direction == "lower_is_better" and a < b) or (
            direction == "higher_is_better" and a > b
        )
        if improved:
            suffix = " ✓"
        elif regressed:
            suffix = " ⚠️"
    return f"| {label} | {a} | {b} | {delta}{suffix} |"


def render_markdown(a: dict, b: dict) -> str:
    a_name = a.get("variant", "A")
    b_name = b.get("variant", "B")
    a_id = a.get("eval_run_id", "?")
    b_id = b.get("eval_run_id", "?")

    lines: list[str] = []
    lines.append(f"# Hook-replay comparison: `{a_name}` vs `{b_name}`")
    lines.append("")
    lines.append(f"- **A: `{a_name}`** — eval-run `{a_id}`, {a.get('queue_record_count', '?')} queue records, {a.get('recall_count', '?')} recalled.")
    lines.append(f"- **B: `{b_name}`** — eval-run `{b_id}`, {b.get('queue_record_count', '?')} queue records, {b.get('recall_count', '?')} recalled.")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")

    # Anti-patterns
    lines.append("## Anti-pattern signatures (lower is better)")
    lines.append("")
    lines.append(f"| metric | {a_name} | {b_name} | delta |")
    lines.append("|---|---:|---:|---:|")
    ap_a, ap_b = a["anti_patterns"], b["anti_patterns"]
    for key in ["session_summary_content", "hallucinated_entity_tags", "platform_unknown"]:
        lines.append(_row(key, ap_a.get(key, 0), ap_b.get(key, 0)))
    lines.append("")

    # Field presence
    lines.append("## Field presence (higher is better — fraction of records with field)")
    lines.append("")
    lines.append(f"| metric | {a_name} | {b_name} | delta |")
    lines.append("|---|---:|---:|---:|")
    fp_a, fp_b = a["field_presence"], b["field_presence"]
    for key in ["with_confidence_pct", "with_origin_session_id_pct", "deploys_with_t_valid_pct"]:
        va = round(fp_a.get(key, 0.0), 3)
        vb = round(fp_b.get(key, 0.0), 3)
        lines.append(_row(key, va, vb, direction="higher_is_better"))
    lines.append("")

    # Content shape
    lines.append("## Content shape — length distribution")
    lines.append("")
    lines.append(f"| bucket | {a_name} | {b_name} | delta |")
    lines.append("|---|---:|---:|---:|")
    cs_a = a["content_shape"]["length_distribution"]
    cs_b = b["content_shape"]["length_distribution"]
    for key in ["le_150", "151_300", "301_1000", "gt_1000"]:
        # Only gt_1000 is unambiguously "lower is better" (oversized records).
        # Other buckets shift as record counts change — informational only.
        direction = "lower_is_better" if key == "gt_1000" else "informational"
        lines.append(_row(key, cs_a.get(key, 0), cs_b.get(key, 0), direction=direction))
    lines.append(_row("near_duplicate_rate", round(a["content_shape"]["near_duplicate_rate"], 3), round(b["content_shape"]["near_duplicate_rate"], 3)))
    lines.append("")

    # Tag drift
    lines.append("## Tag drift (lower is better)")
    lines.append("")
    lines.append(f"| metric | {a_name} | {b_name} | delta |")
    lines.append("|---|---:|---:|---:|")
    td_a, td_b = a["tag_drift"], b["tag_drift"]
    for key in ["jest_collisions", "date_derived_tags"]:
        lines.append(_row(key, td_a.get(key, 0), td_b.get(key, 0)))
    lines.append("")

    # Type validity
    lines.append("## Type validity")
    lines.append("")
    lines.append(f"| metric | {a_name} | {b_name} | delta |")
    lines.append("|---|---:|---:|---:|")
    tv_a, tv_b = a["type_validity"], b["type_validity"]
    lines.append(_row("valid_count", tv_a["valid_count"], tv_b["valid_count"], direction="higher_is_better"))
    lines.append(_row("invalid_count", tv_a["invalid_count"], tv_b["invalid_count"]))
    lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    eliminated: list[str] = []
    untouched: list[str] = []
    regressed: list[str] = []

    def _classify(label: str, a_val, b_val, lower_is_better=True):
        if a_val == b_val:
            untouched.append(f"{label} (unchanged at {a_val})")
        elif (lower_is_better and b_val < a_val) or (not lower_is_better and b_val > a_val):
            eliminated.append(f"{label}: {a_val} → {b_val}")
        else:
            regressed.append(f"{label}: {a_val} → {b_val}")

    for key in ["session_summary_content", "hallucinated_entity_tags", "platform_unknown"]:
        _classify(key, ap_a.get(key, 0), ap_b.get(key, 0))
    _classify("type_validity.invalid_count", tv_a["invalid_count"], tv_b["invalid_count"])
    _classify("tag_drift.jest_collisions", td_a.get("jest_collisions", 0), td_b.get("jest_collisions", 0))
    _classify("tag_drift.date_derived_tags", td_a.get("date_derived_tags", 0), td_b.get("date_derived_tags", 0))

    if eliminated:
        lines.append(f"**Improved by `{b_name}`:**")
        for e in eliminated:
            lines.append(f"- {e}")
        lines.append("")
    if untouched:
        lines.append(f"**Untouched by this single-knob change** (out of scope for `{b_name}`):")
        for u in untouched:
            lines.append(f"- {u}")
        lines.append("")
    if regressed:
        lines.append(f"**Regressed in `{b_name}` ⚠️:**")
        for r in regressed:
            lines.append(f"- {r}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render a markdown comparison of two metrics JSONs")
    p.add_argument("metrics_a", type=Path, help="Metrics JSON for variant A (baseline)")
    p.add_argument("metrics_b", type=Path, help="Metrics JSON for variant B (fix candidate)")
    p.add_argument("--out", type=Path, help="Output markdown file (defaults to stdout)")
    args = p.parse_args(argv)

    a = json.loads(args.metrics_a.read_text())
    b = json.loads(args.metrics_b.read_text())
    md = render_markdown(a, b)

    if args.out:
        args.out.write_text(md)
        print(f"comparison -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
