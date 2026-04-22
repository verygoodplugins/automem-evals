#!/usr/bin/env python3
"""
Judge-agreement study — Phase 2 of the BEAM regression harness plan.

Takes an existing `beam_results_*.json` (already-paid-for hypothesis + rubric
verdicts), re-judges every rubric nugget with a different model (default:
`llama3.3:70b` via Ollama's OpenAI-compatible endpoint), and computes
per-nugget and per-question agreement with the original verdicts.

Usage:
    python3 scripts/rejudge_local.py \\
        data/results/beam/20260421-051827-100K-0_1/beam_results_*.json \\
        --model llama3.3:70b

Exit 0 means agreement was computed; the markdown + JSON outputs land next to
the input. Caller decides whether the rate crosses the threshold in the plan
(≥90 / 80–90 / <80).

Why this exists: switching the regression-harness judge to local inference
saves ~$10/run and makes runs fully deterministic, but only if the local
judge's verdicts track the hosted judge's closely enough. This is the
cheapest way to find out without running a second full 400-Q bucket.

System + user prompts are pulled verbatim from
`third_party/memory-benchmarks/benchmarks/beam/prompts.py` so the only
variable is the model under test.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

# Import BEAM prompts directly from the submodule so we stay in lockstep with
# upstream. This is intentional — if the prompt template drifts, we want the
# rejudge to drift with it, not sit on a stale copy.
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
UPSTREAM = REPO / "third_party" / "memory-benchmarks"
sys.path.insert(0, str(UPSTREAM))
from benchmarks.beam.prompts import (  # noqa: E402
    BEAM_JUDGE_SYSTEM_PROMPT,
    get_beam_nugget_judge_prompt,
)


def call_ollama_judge(
    base_url: str,
    model: str,
    question: str,
    nugget: str,
    llm_response: str,
    timeout: float,
) -> dict:
    """Single judge call. Returns parsed {score, reason}, or raises."""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": BEAM_JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": get_beam_nugget_judge_prompt(question, nugget, llm_response)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        envelope = json.loads(r.read())
    content = envelope["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    # Coerce score to a float that's in the allowed set.
    s = parsed.get("score")
    if isinstance(s, (int, float)):
        parsed["score"] = float(s)
    else:
        # Some models return "1.0" as a string — be forgiving at parse time.
        try:
            parsed["score"] = float(s)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"non-numeric score: {s!r}") from exc
    return parsed


def rejudge_one_question(
    ev: dict,
    base_url: str,
    model: str,
    cutoff_key: str,
    timeout: float,
) -> list[dict]:
    """Re-judge every nugget for one question. Returns a list mirroring
    the original `nugget_scores` shape (nugget, score, reason)."""
    question = ev["question"]
    rubric = ev.get("rubric") or []
    cr = ev.get("cutoff_results", {}).get(cutoff_key) or {}
    llm_response = cr.get("generated_answer") or ""
    out: list[dict] = []
    for nugget in rubric:
        if not isinstance(nugget, str):
            nugget = str(nugget)
        t0 = time.monotonic()
        try:
            parsed = call_ollama_judge(base_url, model, question, nugget, llm_response, timeout)
            parsed["_dt"] = round(time.monotonic() - t0, 2)
            out.append({"nugget": nugget, **parsed})
        except Exception as exc:
            out.append({"nugget": nugget, "score": None, "reason": f"<rejudge error: {exc}>", "_dt": round(time.monotonic() - t0, 2)})
    return out


def load_original_verdicts(ev: dict, cutoff_key: str) -> list[dict]:
    return ev.get("cutoff_results", {}).get(cutoff_key, {}).get("nugget_scores") or []


def summarize_agreement(
    originals: list[list[dict]],
    rejudged: list[list[dict]],
) -> dict:
    """Per-nugget exact-match agreement + per-question PASS/FAIL agreement."""
    nugget_pairs: list[tuple[float | None, float | None]] = []
    per_q_pass_orig: list[bool] = []
    per_q_pass_re: list[bool] = []
    questions_with_scores = 0
    errors = 0
    for orig_list, re_list in zip(originals, rejudged):
        orig_scores: list[float] = []
        re_scores: list[float] = []
        for o, r in zip(orig_list, re_list):
            os_ = o.get("score")
            rs = r.get("score")
            if rs is None:
                errors += 1
                continue
            nugget_pairs.append((float(os_) if isinstance(os_, (int, float)) else None, float(rs)))
            orig_scores.append(float(os_) if isinstance(os_, (int, float)) else 0.0)
            re_scores.append(float(rs))
        # Only include this question in PASS/FAIL agreement if at least one
        # nugget was actually rejudged — otherwise we'd just be counting
        # empty-list agreement.
        if re_scores:
            questions_with_scores += 1
            per_q_pass_orig.append((sum(orig_scores) / len(orig_scores)) >= 0.5)
            per_q_pass_re.append((sum(re_scores) / len(re_scores)) >= 0.5)

    n = len(nugget_pairs)
    exact = sum(1 for a, b in nugget_pairs if a is not None and a == b)
    # Looser: within 0.5 (i.e. off by one tier).
    within = sum(1 for a, b in nugget_pairs if a is not None and abs(a - b) <= 0.5)
    # PASS/FAIL agreement per question.
    passfail_match = sum(1 for a, b in zip(per_q_pass_orig, per_q_pass_re) if a == b)

    # Score-tier distribution
    orig_dist = Counter(a for a, _ in nugget_pairs if a is not None)
    re_dist = Counter(b for _, b in nugget_pairs if b is not None)

    return {
        "nuggets_total": n,
        "errors": errors,
        "exact_match": exact,
        "exact_match_rate": round(exact / n, 3) if n else None,
        "within_one_tier_rate": round(within / n, 3) if n else None,
        "passfail_questions_total": questions_with_scores,
        "passfail_match": passfail_match,
        "passfail_match_rate": round(passfail_match / questions_with_scores, 3) if questions_with_scores else None,
        "orig_score_distribution": dict(sorted(orig_dist.items())),
        "rejudge_score_distribution": dict(sorted(re_dist.items())),
    }


def render_markdown(
    input_path: pathlib.Path,
    model: str,
    stats: dict,
    self_stats: dict | None,
    wall_seconds: float,
) -> str:
    lines: list[str] = []
    lines.append(f"# Judge-agreement study — {model}")
    lines.append("")
    lines.append(f"Input: `{input_path.relative_to(REPO)}`")
    lines.append(f"Re-judger: `{model}` via Ollama `/v1`")
    lines.append(f"Wall-clock: {wall_seconds:.0f}s for {stats['nuggets_total']} nuggets (~{wall_seconds / max(stats['nuggets_total'], 1):.1f}s/nugget)")
    lines.append("")
    lines.append("## Agreement vs original (gpt-5) verdicts")
    lines.append("")
    lines.append(f"- **exact-match rate** (score identical across all 3 tiers): **{stats['exact_match_rate']}** ({stats['exact_match']}/{stats['nuggets_total']})")
    lines.append(f"- within-one-tier rate (off by ≤0.5): {stats['within_one_tier_rate']}")
    lines.append(f"- PASS/FAIL agreement per question (avg nugget ≥ 0.5): **{stats['passfail_match_rate']}** ({stats['passfail_match']}/{stats['passfail_questions_total']})")
    if stats["errors"]:
        lines.append(f"- parse/HTTP errors skipped: {stats['errors']}")
    lines.append("")
    lines.append("## Score-tier distribution")
    lines.append("")
    lines.append("| Tier | Original | Rejudge |")
    lines.append("|---|---|---|")
    for tier in (0.0, 0.5, 1.0):
        lines.append(f"| {tier} | {stats['orig_score_distribution'].get(tier, 0)} | {stats['rejudge_score_distribution'].get(tier, 0)} |")
    lines.append("")
    if self_stats is not None:
        lines.append("## Self-agreement (same model, same prompts, back-to-back)")
        lines.append("")
        lines.append(f"- exact match: **{self_stats['exact_match_rate']}** ({self_stats['exact_match']}/{self_stats['nuggets_total']})")
        lines.append(f"- Expected 1.0 if temp=0 determinism holds. Lower means the model or Ollama isn't deterministic at these inputs — diagnose before trusting it as a judge.")
        lines.append("")
    lines.append("## Plan thresholds")
    lines.append("")
    lines.append("Per `~/.claude/plans/can-you-set-up-synthetic-hoare.md`:")
    lines.append("- ≥ 90% exact-match → adopt as regression judge (both roles local, $0/run).")
    lines.append("- 80–90% → local answerer, hosted judge (~$3/run).")
    lines.append("- < 80% → stay on hosted (~$10/run), slower cadence.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Path to an existing beam_results_*.json")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="llama3.3:70b")
    ap.add_argument("--cutoff", default="top_100", help="Which cutoff's generated_answer to use")
    ap.add_argument("--timeout", type=float, default=600.0, help="Per-call timeout (s). Default generous because llama3.3:70b judge with BEAM's long rubric prompt can run 60-120s cold and more when Ollama is under concurrent load.")
    ap.add_argument("--limit", type=int, default=0, help="Limit questions (0 = all)")
    ap.add_argument("--self-agreement", action="store_true", help="Also run a second pass to measure judge determinism")
    ap.add_argument("--output", default=None, help="Override output path; default: alongside input as *.rejudge-<model>.md/.json")
    args = ap.parse_args()

    input_path = pathlib.Path(args.input).resolve()
    if not input_path.exists():
        raise SystemExit(f"not found: {input_path}")

    data = json.loads(input_path.read_text())
    evaluations = data.get("evaluations") or []
    if args.limit:
        evaluations = evaluations[: args.limit]
    print(f"rejudging {len(evaluations)} questions with {args.model} ...", flush=True)

    originals: list[list[dict]] = []
    rejudged: list[list[dict]] = []
    t_start = time.monotonic()
    for idx, ev in enumerate(evaluations):
        orig = load_original_verdicts(ev, args.cutoff)
        originals.append(orig)
        re_scored = rejudge_one_question(ev, args.base_url, args.model, args.cutoff, args.timeout)
        rejudged.append(re_scored)
        qid = ev.get("question_id", f"q{idx}")
        agreement = sum(
            1 for o, r in zip(orig, re_scored)
            if isinstance(o.get("score"), (int, float)) and isinstance(r.get("score"), (int, float))
            and o["score"] == r["score"]
        )
        print(f"  [{idx+1}/{len(evaluations)}] {qid}: {agreement}/{len(orig)} nuggets exact-match", flush=True)

    wall = time.monotonic() - t_start
    stats = summarize_agreement(originals, rejudged)

    self_stats = None
    if args.self_agreement:
        print("\nrunning self-agreement pass (same model, same prompts, second time)...", flush=True)
        rejudged_again: list[list[dict]] = []
        for ev in evaluations:
            rejudged_again.append(rejudge_one_question(ev, args.base_url, args.model, args.cutoff, args.timeout))
        self_stats = summarize_agreement(rejudged, rejudged_again)

    # Outputs.
    stem = input_path.with_suffix("").name
    safe_model = args.model.replace(":", "-").replace("/", "_")
    out_dir = input_path.parent
    md_path = pathlib.Path(args.output) if args.output else out_dir / f"{stem}.rejudge-{safe_model}.md"
    json_path = md_path.with_suffix(".json")

    payload = {
        "input": str(input_path),
        "model": args.model,
        "base_url": args.base_url,
        "cutoff": args.cutoff,
        "wall_seconds": round(wall, 1),
        "stats": stats,
        "self_stats": self_stats,
        "rejudged": [
            {"question_id": ev.get("question_id"), "nugget_scores": rej}
            for ev, rej in zip(evaluations, rejudged)
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(render_markdown(input_path, args.model, stats, self_stats, wall))

    print(f"\nmarkdown: {md_path.relative_to(REPO)}")
    print(f"json:     {json_path.relative_to(REPO)}")
    print(f"exact-match: {stats['exact_match_rate']} ({stats['exact_match']}/{stats['nuggets_total']})")
    print(f"PASS/FAIL agreement: {stats['passfail_match_rate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
