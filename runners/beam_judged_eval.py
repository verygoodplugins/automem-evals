#!/usr/bin/env python3
"""Native *judged* BEAM harness for AutoMem — produces an official-scorer score.

Unlike ``beam_retrieval_eval.py`` (a deterministic /recall retrieval proxy) and
``run_beam.py`` (which routes AutoMem through a mem0-impersonating shim), this
runner exercises AutoMem's *native* surface end to end:

    ingest (PR #12 chunking + OCCURRED_BEFORE + per-turn time_anchor timestamps)
      -> native /recall (with optional ranking flags: recency_bias, min_score)
      -> answer generation (BEAM's official answer prompt)
      -> rubric nugget judge (BEAM's official 0/0.5/1.0 LLM judge, pass>=0.5)
      -> Kendall tau-b for event_ordering
      -> per-ability + overall metrics (BEAM's official aggregation)

The score is therefore directly comparable to other systems' BEAM numbers *at the
same tier* (e.g. Hindsight 100K = 75%). It is NOT comparable to the 10M headline.

Ingest + the AutoMem HTTP client are imported from ``beam_retrieval_eval`` (PR #12).
The answer prompt, judge prompt, and LLM client are imported from the official BEAM
submodule (``third_party/memory-benchmarks``); the small judge/score orchestration
helpers are ported here verbatim to avoid importing run.py's mem0/pydantic chain.

Requires: OPENAI_API_KEY; upstream deps (``pip install -r
third_party/memory-benchmarks/requirements.txt``, or use ``.venv-beam``); a local
AutoMem stack at http://localhost:8001.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
import statistics
import sys
import time
import uuid
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent
RUNNERS = REPO / "runners"
UPSTREAM = REPO / "third_party" / "memory-benchmarks"
for _p in (str(RUNNERS), str(UPSTREAM)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import beam_retrieval_eval as proxy  # noqa: E402  (PR #12 ingest + AutoMem client)
from benchmarks.beam.prompts import (  # noqa: E402  (official BEAM prompts, zero deps)
    BEAM_JUDGE_SYSTEM_PROMPT,
    get_beam_answer_generation_prompt,
    get_beam_event_alignment_prompt,
    get_beam_fact_extraction_prompt,
    get_beam_nugget_judge_prompt,
)
from benchmarks.common.llm_client import LLMClient  # noqa: E402

logger = logging.getLogger("beam_judged")


def _load_dotenv() -> None:
    """Populate os.environ from REPO/.env for keys not already set (stdlib-only).

    Mirrors runners/run_beam.py so OPENAI_API_KEY in .env is picked up. Existing
    env vars win, so ``env OPENAI_API_KEY=... python ...`` still overrides.
    """
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

DEFAULT_OUTPUT_DIR = REPO / "data" / "results" / "beam-judged"
DEFAULT_ANSWERER_MODEL = "gpt-5"
DEFAULT_JUDGE_MODEL = "gpt-5"
DEFAULT_PROVIDER = "openai"
DEFAULT_TOP_K = 200
DEFAULT_CUTOFFS = (100,)
DEFAULT_RPM = 200
DEFAULT_CONCURRENCY = 4
# gpt-5 is a reasoning model: max_completion_tokens covers reasoning + the answer,
# so the upstream 4096 default truncates long answers (summarization/event_ordering)
# right at the trailing "ANSWER:" -> empty answer -> auto-zero. Give it headroom;
# you are billed for tokens generated, not the cap, so a high ceiling is free.
DEFAULT_ANSWER_MAX_TOKENS = 16384

# Context for honest labelling — published per-tier comparators (leaderboard) and
# the existing mem0-shim baseline produced in this repo by run_beam.py.
LEADERBOARD_100K = {"hindsight": 75.0}
SHIM_BASELINE_100K = {"overall_accuracy": 76.25, "answerer": "gpt-5-mini", "judge": "gpt-5-mini"}

# Usage counters (reset per run; recorded in the artifact metadata).
_USAGE: dict[str, int] = {}


def _reset_usage() -> None:
    _USAGE.clear()
    _USAGE.update(answer_calls=0, nugget_judge_calls=0, event_order_judge_calls=0)


# ---------------------------------------------------------------------------
# Ported BEAM scorer helpers (verbatim from benchmarks/beam/run.py +
# benchmarks/common/{utils,metrics}.py — kept here to avoid importing run.py's
# mem0_client/pydantic dependency chain). Logic is byte-faithful to upstream.
# ---------------------------------------------------------------------------


def cutoff_label(cutoff: int | None) -> str:
    return "all" if cutoff is None else f"top_{cutoff}"


def _clamp_nugget_score(raw_score: float) -> float:
    if raw_score >= 0.75:
        return 1.0
    if raw_score >= 0.25:
        return 0.5
    return 0.0


def compute_kendall_tau_b(predicted_order: list[int], reference_order: list[int]) -> float:
    if len(predicted_order) < 2 or len(reference_order) < 2:
        return 0.0
    pred_rank = {v: i for i, v in enumerate(predicted_order)}
    ref_rank = {v: i for i, v in enumerate(reference_order)}
    common = set(predicted_order) & set(reference_order)
    items = sorted(common)
    if len(items) < 2:
        return 0.0
    concordant = discordant = tied_pred = tied_ref = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            pred_diff = pred_rank[a] - pred_rank[b]
            ref_diff = ref_rank[a] - ref_rank[b]
            if pred_diff == 0 and ref_diff == 0:
                tied_pred += 1
                tied_ref += 1
            elif pred_diff == 0:
                tied_pred += 1
            elif ref_diff == 0:
                tied_ref += 1
            elif (pred_diff > 0 and ref_diff > 0) or (pred_diff < 0 and ref_diff < 0):
                concordant += 1
            else:
                discordant += 1
    n1 = concordant + discordant + tied_pred
    n2 = concordant + discordant + tied_ref
    if n1 == 0 or n2 == 0:
        return 0.0
    return (concordant - discordant) / ((n1 * n2) ** 0.5)


async def judge_single_nugget(
    question: str,
    nugget: str,
    generated_answer: str,
    judge_llm: LLMClient,
) -> dict[str, Any]:
    """Judge a single rubric nugget -> ``{"score": 0.0|0.5|1.0, "reason": ...}``."""
    _USAGE["nugget_judge_calls"] = _USAGE.get("nugget_judge_calls", 0) + 1
    prompt = get_beam_nugget_judge_prompt(question, nugget, generated_answer)
    raw = await judge_llm.generate_structured(system=BEAM_JUDGE_SYSTEM_PROMPT, user=prompt)
    if isinstance(raw, dict):
        try:
            score = _clamp_nugget_score(float(raw.get("score", 0.0)))
        except (ValueError, TypeError):
            score = 0.0
        return {"score": score, "reason": raw.get("reason", "")}
    raw_str = str(raw)
    if "1.0" in raw_str:
        return {"score": 1.0, "reason": raw_str[:200]}
    if "0.5" in raw_str:
        return {"score": 0.5, "reason": raw_str[:200]}
    return {"score": 0.0, "reason": f"Parse error: {raw_str[:200]}"}


async def compute_event_ordering_score(
    question: str,
    rubric_nuggets: list[str],
    generated_answer: str,
    judge_llm: LLMClient,
) -> dict[str, Any]:
    """Kendall tau-b for event_ordering: extract -> align -> correlate."""
    _USAGE["event_order_judge_calls"] = _USAGE.get("event_order_judge_calls", 0) + 1
    extract_raw = await judge_llm.generate_structured(
        system="Extract events as a JSON array of strings.",
        user=get_beam_fact_extraction_prompt(generated_answer),
    )
    extracted_events: list[str] = []
    if isinstance(extract_raw, dict):
        for key in ("events", "facts", "result"):
            if key in extract_raw and isinstance(extract_raw[key], list):
                extracted_events = extract_raw[key]
                break
    elif isinstance(extract_raw, list):
        extracted_events = extract_raw

    if not extracted_events or not rubric_nuggets:
        return {"tau_b": 0.0, "predicted_order": [], "reference_order": []}

    predicted_indices: list[int] = []
    for event in extracted_events:
        _USAGE["event_order_judge_calls"] = _USAGE.get("event_order_judge_calls", 0) + 1
        align_raw = await judge_llm.generate_structured(
            system="Align the event to a reference event index. Return JSON.",
            user=get_beam_event_alignment_prompt(event, rubric_nuggets),
        )
        idx = -1
        if isinstance(align_raw, dict):
            try:
                idx = int(align_raw.get("index", -1))
            except (ValueError, TypeError):
                idx = -1
        if 0 <= idx < len(rubric_nuggets):
            predicted_indices.append(idx)

    reference_order = list(range(len(rubric_nuggets)))
    tau_b = compute_kendall_tau_b(predicted_indices, reference_order)
    return {
        "tau_b": round(tau_b, 4),
        "predicted_order": predicted_indices,
        "reference_order": reference_order,
    }


def _metric_score(cr: dict) -> float:
    """Official per-question score for metrics: the BEAM rubric nugget-mean (`score`).

    For event_ordering questions the harness ALSO computes a Kendall tau-b
    (`event_ordering` + `score_with_tau`), but we deliberately do NOT fold it into
    the official metric here. `score_with_tau` = (rubric + normalized_tau)/2 is a
    local blend, not the upstream BEAM event-ordering score; using it breaks
    leaderboard-comparability and can flip pass/fail (a content-empty but
    perfectly-ordered answer would pass). Scoring event_ordering on the official
    normalized tau-b instead of the rubric is a tracked follow-up — it must match
    the upstream BEAM scorer exactly before it lands in an `official_beam_score`
    artifact. tau-b stays stored on each result for inspection in the meantime."""
    return cr.get("score", 0.0)


def compute_beam_metrics(evaluations: list[dict], cutoffs: list[int]) -> dict[str, Any]:
    """Per-question-type + overall metrics at each cutoff.

    `beam_score` is the BEAM rubric-mean (mean of per-question 0/0.5/1 scores
    ×100) — the AMB-comparable accuracy. `accuracy` is the separate pass-rate at
    threshold 0.5; it is informational and INFLATED vs the rubric-mean whenever
    partial credit (0.5) occurs, so it is NOT the comparable number."""
    from collections import defaultdict

    metrics_by_cutoff: dict[str, Any] = {}
    pass_threshold = 0.5
    for c in cutoffs:
        label = cutoff_label(c)
        scores = [_metric_score(e.get("cutoff_results", {}).get(label, {})) for e in evaluations]
        total = len(scores)
        correct = sum(1 for s in scores if s >= pass_threshold)
        errors = sum(
            1 for e in evaluations if e.get("cutoff_results", {}).get(label, {}).get("error")
        )
        by_type: dict[str, list[dict]] = defaultdict(list)
        for e in evaluations:
            by_type[e.get("question_type", "unknown")].append(e)
        type_metrics: dict[str, dict[str, Any]] = {}
        for qt in sorted(by_type):
            items = by_type[qt]
            qt_scores = [
                _metric_score(i.get("cutoff_results", {}).get(label, {})) for i in items
            ]
            qt_correct = sum(1 for s in qt_scores if s >= pass_threshold)
            type_metrics[qt] = {
                "total": len(items),
                "correct": qt_correct,
                "beam_score": statistics.mean(qt_scores) * 100 if qt_scores else 0.0,
                "accuracy": qt_correct / len(items) * 100 if items else 0.0,  # pass-rate (informational)
                "avg_score": statistics.mean(qt_scores) if qt_scores else 0.0,
            }
        metrics_by_cutoff[label] = {
            "overall": {
                "total": total,
                "correct": correct,
                "errors": errors,
                "beam_score": statistics.mean(scores) * 100 if scores else 0.0,
                "accuracy": correct / total * 100 if total > 0 else 0.0,  # pass-rate (informational)
                "avg_score": statistics.mean(scores) if scores else 0.0,
            },
            "by_question_type": type_metrics,
        }
    return metrics_by_cutoff


# ---------------------------------------------------------------------------
# Native AutoMem recall + answer-memory adapter
# ---------------------------------------------------------------------------


def recall_judged(
    client: "proxy.AutoMemClient",
    question: "proxy.BeamQuestion",
    *,
    run_id: str,
    conv_tag: str,
    limit: int,
    ranking: dict[str, Any] | None,
) -> dict[str, Any]:
    """Tag-scoped native /recall with optional ranking flags (recency_bias, min_score)."""
    params: dict[str, Any] = {
        "query": question.question,
        "tags": [proxy.run_tag(run_id), conv_tag],
        "tag_mode": "all",
        "tag_match": "exact",
        "limit": limit,
    }
    if ranking:
        params.update(ranking)
    t0 = time.perf_counter()
    resp = client.request_json(
        client.endpoint, client.token, "GET", "/recall", params=params, timeout=60
    )
    if isinstance(resp, dict):
        resp["_recall_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return resp


def _result_timestamp(result: dict[str, Any]) -> str:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    ts = memory.get("timestamp") or result.get("timestamp")
    if ts:
        return str(ts)
    # Fall back to the stored time_anchor so the answer prompt still sees a date.
    anchor = proxy.result_metadata(result).get("time_anchor")
    parsed = proxy.parse_time_anchor(anchor) if anchor else None
    return parsed.isoformat() if parsed else ""


def to_answer_memories(recall_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt AutoMem /recall results to BEAM's answer-memory shape, score-desc."""
    results = recall_response.get("results") or []
    formatted: list[dict[str, Any]] = []
    for r in results:
        formatted.append(
            {
                "memory": proxy.result_content(r),
                "created_at": _result_timestamp(r),
                "score": r.get("score") or 0,
                "id": proxy.result_id(r) or "",
            }
        )
    formatted.sort(key=lambda m: m.get("score", 0), reverse=True)
    return formatted


_TOKENIZER: Any = None


def _count_tokens(text: str) -> int:
    """Count tokens in `text` with tiktoken (o200k/cl100k), else a ~chars/4 estimate.

    Used to report context-token footprint per answer prompt — one of the two
    objective, judge-independent axes the public BEAM leaderboard reports
    (alongside recall latency), and the ones our accuracy-only numbers omitted.
    """
    global _TOKENIZER
    if _TOKENIZER is None:
        try:
            import tiktoken

            try:
                _TOKENIZER = tiktoken.get_encoding("o200k_base")
            except Exception:  # noqa: BLE001
                _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001 — tiktoken absent; fall back to estimate
            _TOKENIZER = False
    if _TOKENIZER:
        return len(_TOKENIZER.encode(text))
    return max(1, len(text) // 4)


def retrieval_diagnostics(
    recall_response: dict[str, Any], question: "proxy.BeamQuestion", cutoff: int
) -> dict[str, Any]:
    """Self-triage: did recall surface the question's ground-truth evidence in the
    top-`cutoff` the answerer saw? Reuses the proxy's source-id / rubric scorers so
    every judged run records retrieval quality inline — no separate re-ingest pass
    needed to attribute a FAIL to recall vs the answerer/judge.
    """
    results = (recall_response.get("results") or [])[:cutoff]
    src = set(question.source_chat_ids)
    got: set[int] = set()
    for r in results:
        got |= proxy._source_ids_from_result(r)
    return {
        "source_chat_hit": (bool(src & got) if src else None),
        "n_source": len(src),
        "rubric_overlap": round(
            proxy.score_rubric_overlap(
                question.rubric, [proxy.result_content(r) for r in results]
            ),
            4,
        ),
    }


# ---------------------------------------------------------------------------
# Per-question evaluation (mirrors benchmarks/beam/run.py:process_question)
# ---------------------------------------------------------------------------


async def evaluate_question(
    question: "proxy.BeamQuestion",
    formatted: list[dict[str, Any]],
    *,
    cutoffs: list[int],
    answerer: LLMClient,
    judge: LLMClient,
    answer_max_tokens: int = DEFAULT_ANSWER_MAX_TOKENS,
) -> dict[str, Any]:
    rubric = question.rubric
    result: dict[str, Any] = {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "question": question.question,
        "rubric": rubric,
        "source_chat_ids": question.source_chat_ids,
        "retrieval": {
            "total_results": len(formatted),
            "top_ids": [m.get("id") for m in formatted[:10]],
        },
        "cutoff_results": {},
    }
    for c in cutoffs:
        label = cutoff_label(c)
        # Top-c by score, then chronological (oldest first) for the answer prompt.
        sliced = sorted(formatted[:c], key=lambda m: m.get("created_at", "") or "")
        gen_prompt = get_beam_answer_generation_prompt(question.question, sliced, top_k=c)
        ctx_tokens = _count_tokens(gen_prompt)
        _USAGE["answer_calls"] = _USAGE.get("answer_calls", 0) + 1
        answer = await answerer.generate(system="", user=gen_prompt, max_tokens=answer_max_tokens)
        if "ANSWER:" in answer:
            answer = answer.rsplit("ANSWER:", 1)[-1].strip()

        if not rubric:
            result["cutoff_results"][label] = {
                "judgment": "ERROR",
                "score": 0.0,
                "generated_answer": answer,
                "memories_evaluated": len(sliced),
                "context_tokens": ctx_tokens,
                "nugget_scores": [],
                "error": "No rubric nuggets found",
            }
            continue

        # Nuggets are judged independently and the question score is their (order-
        # invariant) mean, so judging them concurrently is results-identical to the
        # upstream serial loop — only faster. Event_ordering's extract->align stays
        # serial below (alignment depends on the extracted events).
        nugget_raw = await asyncio.gather(
            *(judge_single_nugget(question.question, n, answer, judge) for n in rubric)
        )
        nugget_scores = [
            {"nugget": n, "score": ns["score"], "reason": ns["reason"]}
            for n, ns in zip(rubric, nugget_raw)
        ]
        avg_score = statistics.mean(ns["score"] for ns in nugget_scores) if nugget_scores else 0.0

        cr: dict[str, Any] = {
            "judgment": "PASS" if avg_score >= 0.5 else "FAIL",
            "score": round(avg_score, 4),
            "generated_answer": answer,
            "memories_evaluated": len(sliced),
            "context_tokens": ctx_tokens,
            "nugget_scores": nugget_scores,
        }
        if question.question_type == "event_ordering":
            try:
                tau = await compute_event_ordering_score(question.question, rubric, answer, judge)
                cr["event_ordering"] = tau
                cr["score_with_tau"] = round((avg_score + (tau["tau_b"] + 1.0) / 2.0) / 2.0, 4)
            except Exception as exc:  # noqa: BLE001 — informational, never fails the run
                logger.warning("event_ordering tau-b failed for %s: %s", question.question_id, exc)
        result["cutoff_results"][label] = cr
    return result


# ---------------------------------------------------------------------------
# Judge preflight (live quota/auth check before the question loop; #183 idea)
# ---------------------------------------------------------------------------


def _is_reasoning_model(model: str) -> bool:
    return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))


def judge_preflight(model: str, provider: str) -> None:
    if provider != "openai":
        if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY not set — required for the judge")
        return
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY not set — required for answerer + judge")
    try:
        import openai

        client = openai.OpenAI(api_key=key)
        token_kwarg = (
            {"max_completion_tokens": 5} if _is_reasoning_model(model) else {"max_tokens": 5}
        )
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            **token_kwarg,
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        text = str(exc).lower()
        if any(m in text for m in ("insufficient_quota", "rate limit", "429")):
            raise SystemExit(f"Judge preflight FAILED (quota): {exc}") from exc
        if any(m in text for m in ("invalid_api_key", "unauthorized", "401")):
            raise SystemExit(f"Judge preflight FAILED (auth): {exc}") from exc
        raise SystemExit(f"Judge preflight FAILED (other): {exc}") from exc


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def _health_counts(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_count": health.get("memory_count"),
        "vector_count": health.get("vector_count"),
        "status": health.get("status"),
    }


def build_ranking(args: argparse.Namespace) -> dict[str, Any]:
    ranking: dict[str, Any] = {}
    if args.recency_bias and args.recency_bias != "off":
        ranking["recency_bias"] = args.recency_bias
    if args.min_score is not None:
        ranking["min_score"] = args.min_score
    return ranking


async def run(args: argparse.Namespace) -> dict[str, Any]:
    _reset_usage()
    _load_dotenv()
    proxy.assert_endpoint_allowed(args.endpoint, args.allow_non_local)
    client = proxy.AutoMemClient(args.endpoint, args.token)

    health_before = client.health()
    counts_before = _health_counts(health_before)
    logger.info("AutoMem health before: %s", counts_before)

    judge_preflight(args.judge_model, args.provider)

    answerer = LLMClient(model=args.answerer_model, provider=args.provider, rpm=args.rpm)
    judge = LLMClient(model=args.judge_model, provider=args.provider, rpm=args.rpm)

    rows, dataset_info = proxy.load_beam_rows(
        args.tier,
        dataset_json=pathlib.Path(args.dataset_json) if args.dataset_json else None,
        no_download=args.no_download,
    )
    conversations = proxy.select_conversations(
        rows, tier=args.tier, sample_conversations=args.sample_conversations
    )
    run_id = proxy.new_run_id()
    ranking = build_ranking(args)
    cutoffs = list(args.cutoffs)
    sem = asyncio.Semaphore(args.concurrency)
    evaluations: list[dict[str, Any]] = []
    # Per-conversation checkpoint so a long (multi-hour gpt-5) run survives a
    # mid-run death: completed conversations are flushed as JSONL as we go.
    run_dir = pathlib.Path(args.output_dir) / f"{run_id}-{args.tier}"
    run_dir.mkdir(parents=True, exist_ok=True)
    partial_path = run_dir / "results.partial.jsonl"
    # Resume: seed from a prior run's checkpoint and skip its completed
    # conversations (the killed-overnight-run recovery path).
    resumed_conv_ids: set[str] = set()
    if args.resume_from:
        with open(args.resume_from) as fh, partial_path.open("a") as out:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                evaluations.append(ev)
                resumed_conv_ids.add(ev.get("conversation_id"))
                out.write(line + "\n")
        logger.info(
            "resumed %d questions from %d conversations (%s)",
            len(evaluations),
            len(resumed_conv_ids),
            args.resume_from,
        )
    total_memories = 0
    total_associations = 0

    logger.info(
        "BEAM judged run %s: tier=%s conversations=%d cutoffs=%s ranking=%s timestamps=%s",
        run_id,
        args.tier,
        len(conversations),
        cutoffs,
        ranking or "off",
        not args.no_timestamps,
    )

    try:
        for conv in conversations:
            if conv.conversation_id in resumed_conv_ids:
                logger.info("skip %s (resumed from checkpoint)", conv.conversation_id)
                continue
            chunks = proxy.build_memory_chunks(
                conv, run_id=run_id, with_timestamps=not args.no_timestamps
            )
            memory_ids = client.store_memory_batch(chunks)
            total_associations += client.associate_sequential_chunks(memory_ids)
            total_memories += len(memory_ids)

            questions = conv.questions
            if args.question_limit_per_conv:
                questions = questions[: args.question_limit_per_conv]

            # Bind `conv` as a default arg so each coroutine captures the right
            # conversation even if this gather is ever restructured across iterations.
            async def handle(q: "proxy.BeamQuestion", conv: "proxy.BeamConversation" = conv) -> dict[str, Any]:
                async with sem:
                    recall = await asyncio.to_thread(
                        recall_judged,
                        client,
                        q,
                        run_id=run_id,
                        conv_tag=conv.conversation_tag,
                        limit=args.top_k,
                        ranking=ranking,
                    )
                    formatted = to_answer_memories(recall)
                    ev = await evaluate_question(
                        q,
                        formatted,
                        cutoffs=cutoffs,
                        answerer=answerer,
                        judge=judge,
                        answer_max_tokens=args.answer_max_tokens,
                    )
                    ev["conversation_id"] = conv.conversation_id
                    ev["retrieval"].update(retrieval_diagnostics(recall, q, max(cutoffs)))
                    ev["retrieval"]["recall_latency_ms"] = recall.get("_recall_latency_ms")
                    return ev

            conv_evals = await asyncio.gather(*(handle(q) for q in questions))
            evaluations.extend(conv_evals)
            with partial_path.open("a") as fh:
                for ev in conv_evals:
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            logger.info(
                "conv %s (%d/%d): %d memories, %d questions scored",
                conv.conversation_id,
                conv.conversation_idx + 1,
                len(conversations),
                len(memory_ids),
                len(conv_evals),
            )
            # Fail fast on systemic LLM failure: if a large fraction of answers come
            # back empty, an upstream problem (insufficient_quota / rate limit / auth)
            # is poisoning the run — abort rather than emit a misleadingly low score.
            # Count per answer-generation (one per question*cutoff) so the rate is a
            # true fraction in [0,1] regardless of how many cutoffs are evaluated.
            scored = sum(len(e["cutoff_results"]) for e in evaluations)
            empties = sum(
                1
                for e in evaluations
                for cr in e["cutoff_results"].values()
                if not cr.get("generated_answer") and not cr.get("error")
            )
            if scored >= 40 and empties / scored > args.max_empty_rate:
                raise RuntimeError(
                    f"Aborting after {conv.conversation_idx + 1} conversations: "
                    f"{empties}/{scored} answers empty ({empties / scored:.0%} > "
                    f"{args.max_empty_rate:.0%}) — likely insufficient_quota / rate limit / "
                    f"auth failure. Resolve and re-run; partial results at {partial_path}."
                )
            if not args.keep:
                client.cleanup_run(run_id)  # per-conv scope: tight isolation + small footprint
    finally:
        cleanup_deleted = 0 if args.keep else client.cleanup_run(run_id)
        health_after = client.health()
        counts_after = _health_counts(health_after)
        logger.info("AutoMem health after: %s (cleanup deleted=%s)", counts_after, cleanup_deleted)

    metrics = compute_beam_metrics(evaluations, cutoffs)
    # Inline triage summary: of questions with a ground-truth source, what fraction
    # had the evidence in the answerer's context? (Recall vs answerer/judge split.)
    with_src = [e for e in evaluations if e["retrieval"].get("n_source")]
    retrieval_recall = (
        round(sum(1 for e in with_src if e["retrieval"].get("source_chat_hit")) / len(with_src), 4)
        if with_src
        else None
    )
    # Objective, judge-independent efficiency axes the public BEAM leaderboard reports
    # (recall latency + context tokens). Resumed evals predate this instrumentation, so
    # the summaries cover only questions scored under it (None keys are filtered out).
    def _pct(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]

    recall_ms = [
        e["retrieval"]["recall_latency_ms"]
        for e in evaluations
        if e["retrieval"].get("recall_latency_ms") is not None
    ]
    ctx_toks = [
        cr["context_tokens"]
        for e in evaluations
        for cr in e["cutoff_results"].values()
        if cr.get("context_tokens") is not None
    ]
    efficiency = {
        "recall_latency_ms_mean": round(statistics.mean(recall_ms), 1) if recall_ms else None,
        "recall_latency_ms_median": round(statistics.median(recall_ms), 1) if recall_ms else None,
        "recall_latency_ms_p95": _pct(recall_ms, 0.95),
        "context_tokens_mean": round(statistics.mean(ctx_toks)) if ctx_toks else None,
        "context_tokens_p95": _pct(ctx_toks, 0.95),
        "tokenizer": ("estimate" if _TOKENIZER is False else "tiktoken"),
        "measured_n": len(recall_ms),
    }
    # FalkorDB memory_count is the authoritative leak gate. vector_count is reported
    # too, but Qdrant can carry pre-existing orphaned vectors (sync_status), so we
    # don't hard-fail on vector drift — only on memories not returning to baseline.
    returned_to_baseline = counts_before.get("memory_count") == counts_after.get("memory_count")
    vectors_returned_to_baseline = counts_before.get("vector_count") == counts_after.get(
        "vector_count"
    )
    # Integrity: answers that came back empty (a truncated/failed generation, not a
    # rubric error) are auto-zeroed and depress the score — track them explicitly.
    empty_answers = sum(
        1
        for e in evaluations
        for cr in e["cutoff_results"].values()
        if not cr.get("generated_answer") and not cr.get("error")
    )

    results = {
        "schema": "automem-evals.beam-judged-results.v1",
        "run_id": run_id,
        "run_tag": proxy.run_tag(run_id),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner": "beam-judged",
        "official_beam_score": True,
        "scoring_method": (
            "Official BEAM scorer: LLM rubric-nugget judge (0/0.5/1.0 per nugget, "
            "question score = mean, pass>=0.5), Kendall tau-b for event_ordering."
        ),
        "comparability_note": (
            f"BEAM {args.tier} tier — comparable to other systems' BEAM {args.tier} numbers "
            f"(e.g. Hindsight 100K = {LEADERBOARD_100K['hindsight']}%), NOT the 10M headline."
        ),
        "metadata": {
            "tier": args.tier,
            "answerer_model": args.answerer_model,
            "judge_model": args.judge_model,
            "provider": args.provider,
            "top_k": args.top_k,
            "cutoffs": cutoffs,
            "answer_max_tokens": args.answer_max_tokens,
            "ranking": ranking or {"recency_bias": "off"},
            "with_timestamps": not args.no_timestamps,
            "dataset": dataset_info,
            "conversation_count": len(conversations),
            "total_questions": len(evaluations),
            "memory_count": total_memories,
            "association_count": total_associations,
            "judge_usage": dict(_USAGE),
            "empty_answers": empty_answers,
            "retrieval_recall_at_cutoff": retrieval_recall,
            "efficiency": efficiency,
            "upstream_head": _submodule_head(),
            "health_before": counts_before,
            "health_after": counts_after,
            "cleanup_deleted": cleanup_deleted,
            "returned_to_baseline": returned_to_baseline,
            "vectors_returned_to_baseline": vectors_returned_to_baseline,
            "shim_baseline_100k": SHIM_BASELINE_100K,
        },
        "metrics_by_cutoff": metrics,
        "evaluations": evaluations,
    }
    return results


def _submodule_head() -> str | None:
    head = UPSTREAM / ".git"
    try:
        import subprocess

        out = subprocess.run(
            ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Artifact writing
# ---------------------------------------------------------------------------


def format_report(results: dict[str, Any]) -> str:
    md = results["metadata"]
    lines = [
        f"# BEAM judged report — {results['run_id']}",
        "",
        "Official BEAM scorer (LLM rubric-nugget judge). "
        f"**{md['tier']} tier** — comparable to other systems' BEAM {md['tier']} "
        f"numbers (Hindsight 100K = {LEADERBOARD_100K['hindsight']}%), not the 10M headline.",
        "",
        "## Run",
        "",
        "| field | value |",
        "|---|---|",
        f"| tier | {md['tier']} |",
        f"| answerer | {md['answerer_model']} |",
        f"| judge | {md['judge_model']} ({md['provider']}) |",
        f"| top_k / cutoffs | {md['top_k']} / {md['cutoffs']} |",
        f"| ranking | {md['ranking']} |",
        f"| per-turn timestamps | {md['with_timestamps']} |",
        f"| conversations | {md['conversation_count']} |",
        f"| questions | {md['total_questions']} |",
        f"| memories ingested | {md['memory_count']} |",
        f"| judge usage | {md['judge_usage']} |",
        f"| empty answers | {md.get('empty_answers', 0)} / {md['total_questions']} "
        f"(answer max_tokens={md.get('answer_max_tokens')}) |",
        f"| retrieval recall @cutoff | {md.get('retrieval_recall_at_cutoff')} "
        f"(evidence-in-context for sourced questions) |",
        f"| recall latency (ms) | mean {md.get('efficiency', {}).get('recall_latency_ms_mean')} / "
        f"median {md.get('efficiency', {}).get('recall_latency_ms_median')} / "
        f"p95 {md.get('efficiency', {}).get('recall_latency_ms_p95')} |",
        f"| context tokens | mean {md.get('efficiency', {}).get('context_tokens_mean')} / "
        f"p95 {md.get('efficiency', {}).get('context_tokens_p95')} "
        f"({md.get('efficiency', {}).get('tokenizer')}) |",
        f"| returned to baseline | {md['returned_to_baseline']} "
        f"({md['health_before']} -> {md['health_after']}) |",
        "",
    ]
    for label, m in results["metrics_by_cutoff"].items():
        ov = m["overall"]
        lines += [
            f"## Cutoff {label}",
            "",
            f"**Overall BEAM score: {ov['beam_score']:.2f}%** (rubric-mean, AMB-comparable) "
            f"· pass-rate {ov['accuracy']:.1f}% ({ov['correct']}/{ov['total']}), "
            f"avg_score={ov['avg_score']:.3f}, errors={ov['errors']}",
            "",
            "| ability | BEAM score | pass-rate | avg_score | correct/total |",
            "|---|---|---|---|---|",
        ]
        for qt in sorted(m["by_question_type"]):
            x = m["by_question_type"][qt]
            lines.append(
                f"| {qt} | {x['beam_score']:.1f}% | {x['accuracy']:.1f}% | {x['avg_score']:.3f} | "
                f"{x['correct']}/{x['total']} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_artifacts(results: dict[str, Any], output_dir: pathlib.Path) -> pathlib.Path:
    md = results["metadata"]
    run_dir = output_dir / f"{results['run_id']}-{md['tier']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    (run_dir / "report.md").write_text(format_report(results))
    manifest = {
        "schema": "automem-evals.beam-judged-manifest.v1",
        "run_id": results["run_id"],
        "run_tag": results["run_tag"],
        "created_at": results["created_at"],
        "official_beam_score": True,
        "metadata": md,
    }
    (run_dir / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return run_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_cutoffs(value: str) -> tuple[int, ...]:
    return tuple(int(c.strip()) for c in value.split(",") if c.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", default="100K", help="BEAM tier (default 100K)")
    parser.add_argument(
        "--sample-conversations",
        type=int,
        default=None,
        help="Limit to the first N conversations (smoke tests).",
    )
    parser.add_argument(
        "--question-limit-per-conv",
        type=int,
        default=None,
        help="Limit questions per conversation (smoke tests).",
    )
    parser.add_argument("--answerer-model", default=DEFAULT_ANSWERER_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["openai", "anthropic", "azure"])
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Recall depth.")
    parser.add_argument(
        "--cutoffs",
        type=_parse_cutoffs,
        default=DEFAULT_CUTOFFS,
        help="Comma-separated answer cutoffs (default 100).",
    )
    parser.add_argument(
        "--recency-bias",
        default="off",
        choices=["off", "auto", "on"],
        help="AutoMem /recall recency_bias flag (#194 ranking sweep).",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="AutoMem /recall min_score relevance gate (#194 ranking sweep).",
    )
    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        help="Ablation: ingest WITHOUT mapping time_anchor->timestamp.",
    )
    parser.add_argument(
        "--answer-max-tokens",
        type=int,
        default=DEFAULT_ANSWER_MAX_TOKENS,
        help="max_completion_tokens for answer generation (gpt-5 reasoning needs headroom).",
    )
    parser.add_argument(
        "--max-empty-rate",
        type=float,
        default=0.30,
        help="Abort the run if the empty-answer fraction exceeds this (quota/auth guard).",
    )
    parser.add_argument("--rpm", type=int, default=DEFAULT_RPM, help="LLM requests/min cap.")
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Concurrent questions."
    )
    parser.add_argument("--endpoint", default=proxy.DEFAULT_ENDPOINT)
    parser.add_argument("--token", default=proxy.DEFAULT_TOKEN)
    parser.add_argument("--dataset-json", default=None, help="Explicit dataset JSON path.")
    parser.add_argument("--no-download", action="store_true", help="Fail if dataset not cached.")
    parser.add_argument("--keep", action="store_true", help="Skip cleanup (leave memories).")
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Path to a prior run's results.partial.jsonl; skip its completed conversations.",
    )
    parser.add_argument("--allow-non-local", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        results = asyncio.run(run(args))
    except RuntimeError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 3
    run_dir = write_artifacts(results, pathlib.Path(args.output_dir))
    print(format_report(results))
    print(f"\nArtifacts: {run_dir}")
    md = results["metadata"]
    if not md["returned_to_baseline"]:
        print(
            "WARNING: AutoMem memory/vector counts did not return to baseline "
            f"({md['health_before']} -> {md['health_after']}).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
