#!/usr/bin/env python3
"""Diff two BEAM run results JSON files — produce a per-category delta report.

Usage:
  python3 runners/beam_diff.py A.json B.json [--out report.md]

A is the "before" / baseline, B is the "after" / candidate. Report is emitted
as markdown tables: overall pass rate, per-category pass + avg_score, and a
per-question breakdown of newly-passing and newly-failing questions.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict


def _load(path: pathlib.Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _by_qid(data: dict) -> dict[str, dict]:
    out = {}
    for ev in data.get("evaluations", []):
        qid = ev["question_id"]
        cutoff = ev["cutoff_results"].get("top_100") or next(iter(ev["cutoff_results"].values()))
        out[qid] = {
            "question_type": ev["question_type"],
            "question": ev["question"],
            "score": cutoff["score"],
            "judgment": cutoff["judgment"],
            "generated_answer": cutoff.get("generated_answer", ""),
        }
    return out


def _per_category(by_qid: dict) -> dict:
    agg: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "scores": []})
    for v in by_qid.values():
        a = agg[v["question_type"]]
        a["total"] += 1
        a["correct"] += 1 if v["judgment"] == "PASS" else 0
        a["scores"].append(v["score"])
    return {cat: {
        "total": d["total"],
        "correct": d["correct"],
        "pass_rate": 100.0 * d["correct"] / d["total"] if d["total"] else 0.0,
        "avg_score": sum(d["scores"]) / d["total"] if d["total"] else 0.0,
    } for cat, d in agg.items()}


def _overall(by_qid: dict) -> dict:
    n = len(by_qid)
    correct = sum(1 for v in by_qid.values() if v["judgment"] == "PASS")
    avg = sum(v["score"] for v in by_qid.values()) / n if n else 0.0
    return {"total": n, "correct": correct, "pass_rate": 100.0 * correct / n if n else 0.0, "avg_score": avg}


def _fmt_delta_pp(d: float) -> str:
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.2f}pp"


def _fmt_delta_score(d: float) -> str:
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.3f}"


def build_report(a_path: pathlib.Path, b_path: pathlib.Path) -> str:
    a_data = _load(a_path)
    b_data = _load(b_path)
    a_q = _by_qid(a_data)
    b_q = _by_qid(b_data)

    a_md = a_data.get("metadata", {})
    b_md = b_data.get("metadata", {})

    common_qids = sorted(set(a_q) & set(b_q))
    only_a = sorted(set(a_q) - set(b_q))
    only_b = sorted(set(b_q) - set(a_q))

    lines: list[str] = []
    lines.append(f"# BEAM diff — {a_path.name} vs {b_path.name}")
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append(f"| | A (before) | B (after) |")
    lines.append(f"|---|---|---|")
    for key in ["run_id", "answerer_model", "judge_model", "top_k", "top_k_cutoffs", "chat_sizes", "conversations", "total_questions"]:
        lines.append(f"| {key} | {a_md.get(key, '—')} | {b_md.get(key, '—')} |")
    lines.append("")

    if only_a or only_b:
        lines.append(f"⚠️  Asymmetric question sets: {len(only_a)} only in A, {len(only_b)} only in B, {len(common_qids)} in both.")
        lines.append("All comparisons below use the intersection. Overall numbers report the full set per run.")
        lines.append("")

    # Overall on full set per run
    a_over = _overall(a_q)
    b_over = _overall(b_q)
    lines.append("## Overall")
    lines.append("")
    lines.append("| metric | A | B | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| questions | {a_over['total']} | {b_over['total']} | {b_over['total'] - a_over['total']} |")
    lines.append(f"| pass_rate | {a_over['pass_rate']:.2f}% | {b_over['pass_rate']:.2f}% | {_fmt_delta_pp(b_over['pass_rate'] - a_over['pass_rate'])} |")
    lines.append(f"| avg_score | {a_over['avg_score']:.3f} | {b_over['avg_score']:.3f} | {_fmt_delta_score(b_over['avg_score'] - a_over['avg_score'])} |")
    lines.append("")

    # Per-category (intersect to be fair when question sets differ)
    if only_a or only_b:
        a_int = {q: a_q[q] for q in common_qids}
        b_int = {q: b_q[q] for q in common_qids}
        a_cat = _per_category(a_int)
        b_cat = _per_category(b_int)
        lines.append(f"## Per-category (intersection, n={len(common_qids)})")
    else:
        a_cat = _per_category(a_q)
        b_cat = _per_category(b_q)
        lines.append("## Per-category")
    lines.append("")
    lines.append("| category | n | A pass | B pass | Δ pass | A avg | B avg | Δ avg |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    cats = sorted(set(a_cat) | set(b_cat))
    for cat in cats:
        a = a_cat.get(cat)
        b = b_cat.get(cat)
        if not a or not b:
            continue
        lines.append(
            f"| {cat} | {a['total']} | {a['pass_rate']:.1f}% | {b['pass_rate']:.1f}% "
            f"| {_fmt_delta_pp(b['pass_rate'] - a['pass_rate'])} "
            f"| {a['avg_score']:.3f} | {b['avg_score']:.3f} "
            f"| {_fmt_delta_score(b['avg_score'] - a['avg_score'])} |"
        )
    lines.append("")

    # Flipped questions (PASS → FAIL, FAIL → PASS)
    newly_pass = [q for q in common_qids if a_q[q]["judgment"] == "FAIL" and b_q[q]["judgment"] == "PASS"]
    newly_fail = [q for q in common_qids if a_q[q]["judgment"] == "PASS" and b_q[q]["judgment"] == "FAIL"]
    lines.append("## Question-level flips")
    lines.append("")
    lines.append(f"- Newly passing (A=FAIL → B=PASS): **{len(newly_pass)}**")
    lines.append(f"- Newly failing (A=PASS → B=FAIL): **{len(newly_fail)}**")
    lines.append(f"- Net flips in B's favor: **{len(newly_pass) - len(newly_fail)}**")
    lines.append("")

    if newly_pass:
        lines.append("### Newly passing (sample up to 20)")
        lines.append("")
        for q in newly_pass[:20]:
            a = a_q[q]
            b = b_q[q]
            lines.append(f"- [{a['question_type']}] `{q}` (A score={a['score']:.2f} → B score={b['score']:.2f})")
        if len(newly_pass) > 20:
            lines.append(f"- ...and {len(newly_pass) - 20} more.")
        lines.append("")

    if newly_fail:
        lines.append("### Newly failing (sample up to 20)")
        lines.append("")
        for q in newly_fail[:20]:
            a = a_q[q]
            b = b_q[q]
            lines.append(f"- [{a['question_type']}] `{q}` (A score={a['score']:.2f} → B score={b['score']:.2f})")
        if len(newly_fail) > 20:
            lines.append(f"- ...and {len(newly_fail) - 20} more.")
        lines.append("")

    # Per-category flip balance
    if common_qids:
        cat_flips: dict[str, dict] = defaultdict(lambda: {"up": 0, "down": 0, "both_pass": 0, "both_fail": 0})
        for q in common_qids:
            a = a_q[q]
            b = b_q[q]
            cat = a["question_type"]
            if a["judgment"] == "FAIL" and b["judgment"] == "PASS":
                cat_flips[cat]["up"] += 1
            elif a["judgment"] == "PASS" and b["judgment"] == "FAIL":
                cat_flips[cat]["down"] += 1
            elif a["judgment"] == "PASS":
                cat_flips[cat]["both_pass"] += 1
            else:
                cat_flips[cat]["both_fail"] += 1

        lines.append("### Flip balance per category")
        lines.append("")
        lines.append("| category | ↑ new-pass | ↓ new-fail | net |")
        lines.append("|---|---:|---:|---:|")
        for cat in sorted(cat_flips):
            f = cat_flips[cat]
            net = f["up"] - f["down"]
            sign = "+" if net >= 0 else ""
            lines.append(f"| {cat} | {f['up']} | {f['down']} | {sign}{net} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=pathlib.Path, help="Baseline (before) results JSON")
    ap.add_argument("b", type=pathlib.Path, help="Candidate (after) results JSON")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="Write markdown to file")
    args = ap.parse_args()

    if not args.a.exists():
        raise SystemExit(f"file not found: {args.a}")
    if not args.b.exists():
        raise SystemExit(f"file not found: {args.b}")

    md = build_report(args.a, args.b)
    if args.out:
        args.out.write_text(md)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
