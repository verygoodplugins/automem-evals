#!/usr/bin/env python3
"""Side-by-side question-level comparison between two BEAM runs.

For a given question_id, print:
  - the question + rubric + ground truth
  - A's retrieved memories + A's answer + A's score
  - B's retrieved memories + B's answer + B's score
  - judge reasoning in both

Useful for understanding *why* a question flipped between runs.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Optional


def _find_eval(path: pathlib.Path, qid: str) -> Optional[dict]:
    with path.open() as f:
        data = json.load(f)
    for ev in data["evaluations"]:
        if ev["question_id"] == qid:
            return ev
    return None


def _dump_eval(ev: dict, label: str, n_mems: int = 10) -> str:
    cutoff = ev["cutoff_results"]["top_100"]
    lines = []
    lines.append(f"=== {label} ===")
    lines.append(f"judgment: {cutoff['judgment']}  score: {cutoff['score']}")
    lines.append(f"generated_answer: {(cutoff.get('generated_answer') or '')[:800]}")
    lines.append("")
    nug = cutoff.get("nugget_scores") or []
    for ns in nug:
        lines.append(f"  [nugget score={ns.get('score')}] {ns.get('nugget', '')[:120]}")
        lines.append(f"     reason: {(ns.get('reason') or '')[:400]}")
    lines.append("")
    results = ev["retrieval"]["search_results"][:n_mems]
    lines.append(f"top {len(results)} retrieved (of {ev['retrieval']['total_results']}):")
    for i, r in enumerate(results):
        mem = r.get("memory")
        if isinstance(mem, dict):
            content = mem.get("content", "") or mem.get("memory", "")
        else:
            content = mem or ""
        score = r.get("score")
        score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
        lines.append(f"  [{i+1}] score={score_str}: {str(content)[:300]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("qid", help="e.g. 100K_0_q19_temporal_reasoning")
    ap.add_argument("--a", type=pathlib.Path,
                    default=pathlib.Path("data/results/beam/20260421-234814-100K-0_19/beam_results_20260422_035020.json"),
                    help="Run A (default: V1 full baseline)")
    ap.add_argument("--b", type=pathlib.Path, required=True, help="Run B (e.g. V2 results JSON)")
    ap.add_argument("--n-mems", type=int, default=10)
    args = ap.parse_args()

    a_ev = _find_eval(args.a, args.qid)
    b_ev = _find_eval(args.b, args.qid)
    if not a_ev:
        print(f"A: question_id not found: {args.qid}")
        return 1
    if not b_ev:
        print(f"B: question_id not found: {args.qid}")
        return 1

    print(f"QUESTION_ID: {args.qid}")
    print(f"type: {a_ev['question_type']}")
    print(f"conversation_idx: {a_ev['conversation_idx']}")
    print(f"difficulty: {a_ev['difficulty']}")
    print(f"question: {a_ev['question']}")
    print(f"ground_truth: {(a_ev.get('ground_truth_answer') or '')[:400]}")
    print(f"rubric: {json.dumps(a_ev.get('rubric'), ensure_ascii=False)[:500]}")
    print()

    print(_dump_eval(a_ev, "A (baseline)", n_mems=args.n_mems))
    print()
    print(_dump_eval(b_ev, "B (candidate)", n_mems=args.n_mems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
