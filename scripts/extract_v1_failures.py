#!/usr/bin/env python3
"""Extract the 95 FAIL-judged questions from the V1 baseline into a compact
per-question view suitable for classification.

Output shape (one JSON file, list of dicts):
  question_id, question_type, conversation_idx, difficulty,
  question, rubric (nugget texts), ground_truth_answer, generated_answer,
  score, judge_reasons (list, from nugget_scores),
  retrieved_count, top_memories (first N memories with score + content preview)

We trim each memory preview to 800 chars so the aggregated JSON stays under
a few MB and is fast to iterate on.
"""
from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "data/results/beam/20260421-234814-100K-0_19/beam_results_20260422_035020.json"
OUT = REPO / "data/results/beam/20260421-234814-100K-0_19/failures_v1.json"
MEMORY_PREVIEW_CHARS = 800
TOP_MEMORIES = 20


def main() -> int:
    with SRC.open() as f:
        data = json.load(f)

    out = []
    for ev in data["evaluations"]:
        cutoff = ev["cutoff_results"]["top_100"]
        if cutoff["judgment"] != "FAIL":
            continue

        retrieved = ev["retrieval"]["search_results"][:TOP_MEMORIES]
        top = []
        for r in retrieved:
            mem = r.get("memory") or ""
            if isinstance(mem, dict):
                mem = mem.get("content", "") or mem.get("memory", "")
            top.append({
                "id": r.get("id"),
                "score": r.get("score"),
                "content": (mem or "")[:MEMORY_PREVIEW_CHARS],
            })

        rubric = ev.get("rubric") or []
        # Rubric can be a list of strings (nugget texts) or richer dicts
        if rubric and isinstance(rubric[0], dict):
            rubric_texts = [r.get("nugget") or r.get("text") or str(r) for r in rubric]
        else:
            rubric_texts = list(rubric)

        nugget_scores = cutoff.get("nugget_scores") or []
        judge_reasons = [
            {
                "nugget": ns.get("nugget"),
                "score": ns.get("score"),
                "reason": ns.get("reason"),
            }
            for ns in nugget_scores
        ]

        out.append({
            "question_id": ev["question_id"],
            "question_type": ev["question_type"],
            "conversation_idx": ev["conversation_idx"],
            "conversation_id": ev["conversation_id"],
            "difficulty": ev["difficulty"],
            "question": ev["question"],
            "rubric": rubric_texts,
            "ground_truth_answer": ev["ground_truth_answer"],
            "generated_answer": cutoff["generated_answer"],
            "score": cutoff["score"],
            "memories_evaluated": cutoff["memories_evaluated"],
            "total_retrieved": ev["retrieval"]["total_results"],
            "search_query": ev["retrieval"]["search_query"],
            "judge_reasons": judge_reasons,
            "top_memories": top,
        })

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(REPO)}  ({len(out)} failures, {OUT.stat().st_size} bytes)")
    # Per-category counts
    from collections import Counter
    c = Counter(f["question_type"] for f in out)
    for cat, n in sorted(c.items()):
        print(f"  {cat:30s} {n:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
