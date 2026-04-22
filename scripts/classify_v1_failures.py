#!/usr/bin/env python3
"""Classify each V1 failure into one of five failure modes using gpt-5-mini.

Input:  data/results/beam/20260421-234814-100K-0_19/failures_v1.json
Output: data/results/beam/20260421-234814-100K-0_19/failures_v1_classified.json

Failure-mode taxonomy (locked before running so results are not p-hacked):
  A — retrieval_miss        The ground-truth-bearing chunk is NOT present in top_memories.
                             Answerer had no chance; recall/ranking is the problem.
  B — chronology_confusion  Ground-truth chunk IS in top_memories and contains both old
                             and new fact, but the generated answer cites the old/wrong
                             one. Classic V1-shim knowledge_update failure.
  C — answerer_ignored      Ground-truth chunk IS in top_memories with a clear, unambiguous
                             fact, but the generated answer does not use it (picks
                             distractors, off-topic, or contradicts retrieved evidence).
  D — no_ground_truth       NONE of the retrieved memories contain anything resembling
                             the ground-truth-bearing fact. Likely corpus/ingestion gap
                             (50K truncation, missing turn, or BEAM data issue).
  E — hallucination_or_no_abstain   Answer fabricates or confabulates. For the abstention
                             category specifically: the answerer SHOULD have said "no
                             information available" but produced a confident wrong answer.
  F — other                  Edge cases that don't fit (mark for manual review).

Implications for V2 shim:
  A-heavy category → fact extraction may help (smaller atomic memories = better ranking).
  B-heavy category → STRONGLY implies extraction helps (distinct memories enable
                      supersession edges).
  C-heavy category → answerer prompt or retrieval is the bottleneck, not ingestion.
  D-heavy category → corpus/ingestion bug (50K cap or upstream issue).
  E-heavy category → answerer-side; V2 shim won't fix it.

Phase-2 decision gate (pre-committed):
  * If ≥60% of knowledge_update failures are A or B → proceed with V2 extraction shim.
  * If <60% are A/B AND majority are C or E → skip V2, pivot to answerer/retrieval fix.
  * For other categories the classification is reporting, not decision-gating.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "data/results/beam/20260421-234814-100K-0_19/failures_v1.json"
OUT = REPO / "data/results/beam/20260421-234814-100K-0_19/failures_v1_classified.json"
MODEL = "gpt-5-mini"
MAX_WORKERS = 8
TOP_MEMS_IN_PROMPT = 10  # trim to keep prompt size reasonable


SYSTEM = """You are a failure-mode classifier for memory-augmented QA.

Classify a single FAILED question into exactly one bucket:

A — retrieval_miss:  The ground-truth-bearing content is NOT present in ANY of the retrieved top_memories.
B — chronology_confusion:  A retrieved memory contains BOTH the old and the new/correct fact (the signature pattern is a knowledge update inside raw dialogue — the user switches from X to Y in the same chunk), and the generated answer cites the old one.
C — answerer_ignored:  A retrieved memory contains the correct fact cleanly, but the generated answer ignores it and picks a wrong one, or gives an off-topic answer.
D — no_ground_truth:  Reviewing the retrieved memories, NONE of them contain the evidence needed. This is different from A only when the rubric text names a specific fact that should exist; use D when it looks like the underlying conversation never had it.
E — hallucination_or_no_abstain:  The answer fabricates specifics, or — for abstention questions where the correct answer is 'no information available' — the answer makes up a confident claim.
F — other:  Genuinely doesn't fit A–E.

Output STRICT JSON: {"bucket": "A"|"B"|"C"|"D"|"E"|"F", "confidence": 0.0..1.0, "one_line_reason": "..."}
"""


def _load_dotenv() -> None:
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v


def _build_user_prompt(f: dict) -> str:
    mems = f["top_memories"][:TOP_MEMS_IN_PROMPT]
    mem_lines = []
    for i, m in enumerate(mems):
        content = (m.get("content") or "").replace("\n", " ")[:400]
        mem_lines.append(f"[{i+1}] score={m.get('score'):.3f}: {content}")
    mem_block = "\n".join(mem_lines) if mem_lines else "(no memories retrieved)"

    reasons = f.get("judge_reasons") or []
    reason_block = "\n".join(
        f"- nugget={r['nugget']!r} score={r['score']}: {r.get('reason', '')[:300]}"
        for r in reasons[:4]
    )

    return f"""CATEGORY: {f['question_type']}
QUESTION: {f['question']}
GROUND TRUTH ANSWER (rubric): {f['ground_truth_answer']}
RUBRIC NUGGETS: {json.dumps(f['rubric'], ensure_ascii=False)[:1200]}

GENERATED ANSWER: {(f['generated_answer'] or '')[:1500]}

JUDGE REASONING:
{reason_block}

TOP {len(mems)} RETRIEVED MEMORIES (of {f.get('total_retrieved', '?')} total):
{mem_block}

Classify per the taxonomy. Return JSON only.
"""


def classify_one(client: openai.OpenAI, f: dict) -> dict:
    prompt = _build_user_prompt(f)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            reasoning_effort="minimal",
        )
        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return {
            "question_id": f["question_id"],
            "question_type": f["question_type"],
            "conversation_idx": f["conversation_idx"],
            "bucket": parsed.get("bucket", "F"),
            "confidence": float(parsed.get("confidence", 0.0)),
            "one_line_reason": parsed.get("one_line_reason", ""),
            "score": f["score"],
        }
    except Exception as exc:
        return {
            "question_id": f["question_id"],
            "question_type": f["question_type"],
            "conversation_idx": f["conversation_idx"],
            "bucket": "ERROR",
            "confidence": 0.0,
            "one_line_reason": f"classifier error: {exc}",
            "score": f["score"],
        }


def main() -> int:
    _load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set")

    with SRC.open() as f:
        failures = json.load(f)

    client = openai.OpenAI()
    print(f"Classifying {len(failures)} failures with {MODEL} (max_workers={MAX_WORKERS})")
    start = time.monotonic()

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(classify_one, client, f): f["question_id"] for f in failures}
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            if i % 10 == 0 or i == len(failures):
                print(f"  [{i}/{len(failures)}] {res['question_type']:30s} {res['bucket']} — {res['one_line_reason'][:70]}")

    dt = time.monotonic() - start
    print(f"\nClassification done in {dt:.1f}s")

    # Aggregate distribution
    from collections import Counter, defaultdict
    per_cat: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        per_cat[r["question_type"]][r["bucket"]] += 1
    total = Counter()
    for r in results:
        total[r["bucket"]] += 1

    OUT.write_text(json.dumps({
        "model": MODEL,
        "total_failures": len(failures),
        "overall_distribution": dict(total),
        "by_category": {cat: dict(c) for cat, c in per_cat.items()},
        "per_failure": results,
    }, indent=2))
    print(f"\nwrote {OUT.relative_to(REPO)}")

    print("\nOverall bucket distribution:")
    for b, n in sorted(total.items()):
        pct = 100 * n / len(failures)
        print(f"  {b}: {n:>3} ({pct:4.1f}%)")

    print("\nPer-category:")
    print(f"  {'category':30s} {'A':>3} {'B':>3} {'C':>3} {'D':>3} {'E':>3} {'F':>3} {'ERROR':>6}")
    for cat in sorted(per_cat):
        c = per_cat[cat]
        print(f"  {cat:30s} {c.get('A',0):>3} {c.get('B',0):>3} {c.get('C',0):>3} {c.get('D',0):>3} {c.get('E',0):>3} {c.get('F',0):>3} {c.get('ERROR',0):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
