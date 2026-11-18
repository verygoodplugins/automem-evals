#!/usr/bin/env python3
"""Offline scaffold for MemOps lifecycle-operation probes (arXiv:2607.12893).

Stdlib only. No network, model or AutoMem calls: it validates MemOps evidence
records, turns their gold operation traces into AutoMem write plans for four
write arms, builds recall plans per probe, defines the deterministic recall-side
classifiers and per-operation aggregation, and emits a ``not_scored`` report.
The CLI has no recall transport, so it cannot produce a score. Paper numbers
are baselines and never AutoMem scores. See docs/eval/memops.md.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "automem-evals.memops.v1"
UPSTREAM = {
    "repo": "https://github.com/MemTensor/MemOps",
    "commit": "312af65e2c7b6d1b70f062ffa8b4cde32aaf6f35",
    "license": "MIT",
    "evidence_dir": "generated_result/2-evidence_conversation",
    "evidence_files": 403,
    # sha256 over sorted "<name>\0<sha256(file bytes)>\n" lines of the *.json files.
    "evidence_digest_sha256": "2b819b54d66a71d8070f1b953016e2274dd5584e5b1a1b1ba89732bc3727b70e",
}
# Contract read at automem origin/develop (docs/API.md, automem/api/memory.py).
AUTOMEM_CONTRACT = {
    "pin": "1a7ba1a6afe69835f62ad7f6013e33301d1ab83e",
    "recall_state_mode": "current (default) | history",
    "patch_fields": "content, tags, importance, type, confidence, timestamp, metadata, t_valid, t_invalid",
    "supersession_relations": ("INVALIDATED_BY", "EVOLVED_INTO"),
    "derivation_relation": "DERIVED_FROM",
}
OPERATIONS = ("remember", "forget", "update", "reflect")
PROBES = (
    "OperationTrace", "TargetBinding", "StateTransition", "CandidateDisambiguation",
    "OperationApplication", "StateTrajectory",
)
SETTINGS = ("adjacent_operation", "longitudinal_operation")
VARIANTS = ("cold", "matured")
# raw_turns is the control: every user turn, no lifecycle calls. The oracle_* arms
# drive writes from the GOLD trace, so they are upper bounds for a lifecycle
# writer, not what an agent would infer; an inferring arm needs a paid extractor.
ARMS = ("raw_turns", "oracle_lifecycle_soft", "oracle_lifecycle_hard", "oracle_inplace")
# Probes that need the before-state read history; the rest read current state.
STATE_MODE = {
    "OperationTrace": "history", "StateTransition": "history", "StateTrajectory": "history",
    "TargetBinding": "current", "CandidateDisambiguation": "current",
    "OperationApplication": "current",
}
BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)  # synthetic narrative clock
TENTATIVE_CONFIDENCE = 0.3


class PinMismatch(Exception):
    """The local MemOps data does not match the pinned revision."""


class CoverageError(Exception):
    """Aggregation was asked to score an incomplete result set."""


def narrative_ts(conversation_index, turn_index):
    """Deterministic timestamp: one day per conversation, one minute per turn."""
    when = BASE_TIME + timedelta(days=conversation_index - 1, minutes=turn_index)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def evidence_digest(directory):
    files = sorted(Path(directory).glob("*.json"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(f"{path.name}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    return len(files), digest.hexdigest()


def verify_pin(memops_dir):
    """Fail closed unless the evidence directory is the pinned revision."""
    count, digest = evidence_digest(Path(memops_dir) / UPSTREAM["evidence_dir"])
    if count != UPSTREAM["evidence_files"] or digest != UPSTREAM["evidence_digest_sha256"]:
        raise PinMismatch(f"evidence files {count}, digest {digest}; expected pin {UPSTREAM['commit']}")
    return digest


def validate_record(record):
    """Structural checks the plans rely on. Raises ValueError on the first defect."""
    for key in ("target_fact", "operation_type", "conversations", "operations", "answer"):
        if key not in record:
            raise ValueError(f"missing key {key}")
    segments = {c["segment_index"]: c["dialogue"] for c in record["conversations"]}
    for op in record["operations"]:
        if op["type"] not in OPERATIONS:
            raise ValueError(f"{op.get('operation_id')}: unknown operation type {op['type']}")
        for span in [op["trigger_span"], *op["evidence_spans"]]:
            dialogue = segments.get(span["segment_index"])
            if dialogue is None or not 1 <= span["turn_index"] <= len(dialogue):
                raise ValueError(f"{op['operation_id']}: span outside the conversation")
            if dialogue[span["turn_index"] - 1]["role"] != "user":
                raise ValueError(f"{op['operation_id']}: span is not a user turn")
    for question in record["answer"]:
        if question["evaluation_type"] not in PROBES or question["evaluation_setting"] not in SETTINGS:
            raise ValueError(f"{question.get('question_pair_id')}: unknown probe or setting")
    return record


def locate_evidence(evidence, injected):
    """Map evidence segment -> (conversation index, dialogue offset) in an injected record.

    ``conversation_index`` is 1-based and the evidence messages sit at
    ``dialogue[insertion_index:insertion_index + evidence_message_count]``; the
    text is compared so a layout change fails closed.
    """
    segments = {c["segment_index"]: c["dialogue"] for c in evidence["conversations"]}
    located = {}
    for ins in injected["injection_metadata"]["insertions"]:
        conv = injected["conversations"][ins["conversation_index"] - 1]["dialogue"]
        start, count = ins["insertion_index"], ins["evidence_message_count"]
        want = [m["content"] for m in segments[ins["evidence_segment_index"]]]
        if [m["content"] for m in conv[start:start + count]] != want:
            raise ValueError(f"segment {ins['evidence_segment_index']} not found at its insertion offset")
        located[ins["evidence_segment_index"]] = (ins["conversation_index"], start)
    return located


def _tags(run_tag, record_id, *extra):
    return ["memops", f"memops:{run_tag}", f"memops:conv:{record_id}", *extra]


def ingest_plan(evidence, *, setting, arm, run_tag, record_id, injected=None):
    """Symbolic write plan; ``ref`` names stand in for server-assigned ids."""
    if arm not in ARMS or setting not in SETTINGS:
        raise ValueError("unknown arm or setting")
    validate_record(evidence)
    longitudinal = setting == "longitudinal_operation"
    if longitudinal and injected is None:
        raise ValueError("longitudinal_operation needs the injected record")
    located = locate_evidence(evidence, injected) if longitudinal else {}
    lifecycle = arm != "raw_turns"
    steps, warnings = [], []
    refs = {}  # (segment, turn) -> ref

    def position(segment, turn):
        if longitudinal:
            conv, start = located[segment]
            return conv, start + turn
        return segment, turn

    def store(ref, content, ts, tags, *, memory_type="Context", confidence=0.9, role="evidence"):
        steps.append({"step": "store", "ref": ref, "role": role, "body": {
            "content": content, "type": memory_type, "importance": 0.6,
            "confidence": confidence, "timestamp": ts, "t_valid": ts, "tags": tags}})

    segments = {c["segment_index"]: c["dialogue"] for c in evidence["conversations"]}
    if longitudinal:  # carrier and distractor turns are filler in every arm
        evidence_slots = {(c, s + t) for seg, (c, s) in located.items()
                          for t in range(1, len(segments[seg]) + 1)}
        for ci, conv in enumerate(injected["conversations"], start=1):
            for ti, msg in enumerate(conv["dialogue"], start=1):
                if msg["role"] == "user" and (ci, ti) not in evidence_slots:
                    store(f"f{ci}t{ti}", msg["content"], narrative_ts(ci, ti),
                          _tags(run_tag, record_id, "memops:role:filler"), role="filler")
    if not lifecycle:
        for seg, dialogue in segments.items():
            for ti, msg in enumerate(dialogue, start=1):
                if msg["role"] == "user":
                    ref, (ci, pos) = f"c{seg}t{ti}", position(seg, ti)
                    refs[(seg, ti)] = ref
                    store(ref, msg["content"], narrative_ts(ci, pos), _tags(run_tag, record_id))
        return {"steps": steps, "warnings": warnings, "arm": arm, "setting": setting}

    current, bound = {}, defaultdict(list)  # target -> current ref / every ref ever bound

    def ensure_turn(segment, turn, op, extra_tags=()):
        key = (segment, turn)
        if key not in refs:
            ref, (ci, pos) = f"c{segment}t{turn}", position(segment, turn)
            refs[key] = ref
            text = segments[segment][turn - 1]["content"]
            tags = _tags(run_tag, record_id, f"memops:op:{op['type']}",
                         f"memops:validity:{op['validity']}", *extra_tags)
            conf = TENTATIVE_CONFIDENCE if op["validity"] == "tentative" else 0.9
            store(ref, text, narrative_ts(ci, pos), tags, confidence=conf)
        return refs[key]

    ordered = sorted(evidence["operations"], key=lambda o: (
        o["trigger_span"]["segment_index"], o["trigger_span"]["turn_index"]))
    invalidated = set()
    for op in ordered:
        seg, turn = op["trigger_span"]["segment_index"], op["trigger_span"]["turn_index"]
        ci, pos = position(seg, turn)
        ts, target = narrative_ts(ci, pos), op["target"]["target_id"]
        tag = f"memops:target:{target}"
        if op["validity"] == "retracted":
            steps.append({"step": "skip", "op_id": op["operation_id"], "reason": "retracted"})
        elif op["type"] == "forget":
            if not bound[target]:
                warnings.append(f"{op['operation_id']}: forget without a bound memory")
            for ref in bound[target]:  # every memory ever bound, tentative ones included
                if arm == "oracle_lifecycle_hard":
                    steps.append({"step": "delete", "ref": ref})
                elif ref not in invalidated:
                    steps.append({"step": "patch", "ref": ref, "body": {"t_invalid": ts}})
                    invalidated.add(ref)
            bound[target] = []
            current.pop(target, None)
        elif op["type"] == "reflect":
            ref = f"{op['operation_id']}r"
            store(ref, op["new_value"], ts,
                  _tags(run_tag, record_id, "memops:op:reflect", f"memops:validity:{op['validity']}", tag),
                  memory_type="Insight",
                  confidence=TENTATIVE_CONFIDENCE if op["validity"] == "tentative" else 0.9)
            for span in op["evidence_spans"]:
                src = ensure_turn(span["segment_index"], span["turn_index"], op, (tag,))
                steps.append({"step": "associate", "from": ref, "to": src, "type": "DERIVED_FROM",
                              "strength": 1.0})
        elif op["validity"] == "tentative":
            bound[target].append(ensure_turn(seg, turn, op, (tag,)))  # never becomes current
        elif op["type"] == "update" and arm == "oracle_inplace" and target in current:
            steps.append({"step": "patch", "ref": current[target], "body": {
                "content": segments[seg][turn - 1]["content"], "timestamp": ts, "t_valid": ts}})
        else:
            new = ensure_turn(seg, turn, op, (tag,))
            old = current.get(target)
            if op["type"] == "update" and old is None:
                warnings.append(f"{op['operation_id']}: update without a predecessor")
            if op["type"] == "update" and old is not None:
                steps.append({"step": "patch", "ref": old, "body": {"t_invalid": ts}})
                invalidated.add(old)
                steps.append({"step": "associate", "from": old, "to": new,
                              "type": "INVALIDATED_BY", "strength": 1.0})
            current[target] = new
            bound[target].append(new)
    return {"steps": steps, "warnings": warnings, "arm": arm, "setting": setting}


def recall_plan(evidence, *, setting, run_tag, record_id, limit=10):
    """One /recall request per question. Gold fields stay in ``labels`` only."""
    plan = []
    for q in evidence["answer"]:
        if q["evaluation_setting"] != setting:
            continue
        rubric, checks = q["judge_rubric"], q["diagnostic_checks"]
        plan.append({
            # question_pair_id repeats across records and settings (8 distinct ids over
            # 4,012 questions at the pin), so the composite identity travels with the plan.
            "record_id": record_id, "setting": setting,
            "question_pair_id": q["question_pair_id"], "probe": q["evaluation_type"],
            "operation_type": evidence["operation_type"],
            "params": {"query": q["question"], "tags": _tags(run_tag, record_id)[1:],
                       "tag_mode": "all", "tag_match": "exact", "limit": limit,
                       "state_mode": STATE_MODE[q["evaluation_type"]]},
            "labels": {"must_include": list(rubric.get("must_include") or []),
                       "must_not_include": list(rubric.get("must_not_include") or []),
                       "stale_value": checks.get("stale_value")}})
    return plan


def classify_recall(labels, recalled_texts):
    """Deterministic recall-side lower bound (substring, case-insensitive).

    ``leak`` is None when the question carries no must_not_include label: an
    unlabeled question is unknown, never a zero leak rate.
    """
    text = "\n".join(recalled_texts).casefold()
    must, banned = labels["must_include"], labels["must_not_include"]
    return {
        "support": all(m.casefold() in text for m in must) if must else None,
        "leak": any(b.casefold() in text for b in banned) if banned else None,
    }


def _question_key(item):
    """Composite identity of one question: ids repeat across records and settings."""
    try:
        return (item["record_id"], item["setting"], item["question_pair_id"])
    except KeyError as exc:
        raise ValueError(f"missing {exc.args[0]} on {sorted(item)}") from None


def _index_by_question(items, what):
    by_key = {}
    for item in items:
        key = _question_key(item)
        if key in by_key:  # a silent overwrite would let one record cover another
            raise ValueError(f"duplicate {what} for {key}")
        by_key[key] = item
    return by_key


def aggregate(plans, results):
    """Per-(operation, probe, setting) recall diagnostics; refuses incomplete coverage.

    Plans and results are matched on (record_id, setting, question_pair_id).
    """
    planned = _index_by_question(plans, "planned question")
    by_key = _index_by_question(results, "result")
    missing = [key for key in planned if key not in by_key]
    if missing:
        raise CoverageError(f"{len(missing)} planned questions have no result")
    cells = defaultdict(lambda: {"n": 0, "support_labeled": 0, "support_hits": 0,
                                 "leak_labeled": 0, "leaks": 0})
    for key, plan in planned.items():
        verdict = classify_recall(plan["labels"], by_key[key]["recalled"])
        cell = cells[(plan["operation_type"], plan["probe"], plan["setting"])]
        cell["n"] += 1
        if verdict["support"] is not None:
            cell["support_labeled"] += 1
            cell["support_hits"] += verdict["support"]
        if verdict["leak"] is not None:
            cell["leak_labeled"] += 1
            cell["leaks"] += verdict["leak"]
    out = []
    for (op, probe, setting), c in sorted(cells.items()):
        out.append({"operation_type": op, "probe": probe, "setting": setting, **c,
                    "support_rate": c["support_hits"] / c["support_labeled"] if c["support_labeled"] else None,
                    "leak_rate": c["leaks"] / c["leak_labeled"] if c["leak_labeled"] else None})
    return out


def build_report(summaries):
    """Always not_scored: per-probe cells never carry final-answer accuracy."""
    return {
        "schema": SCHEMA, "status": "not_scored", "paper_comparable": False,
        "final_answer_accuracy": None, "upstream": UPSTREAM, "automem_contract": AUTOMEM_CONTRACT,
        "variants": {v: {"status": "not_scored", "probe_cells": [],
                         "maintenance": "none" if v == "cold" else "frozen maturation profile, not run"}
                     for v in VARIANTS},
        "plan_summaries": summaries,
        "note": "No recall transport and no model calls; paper figures are baselines, not AutoMem results.",
    }


def summarize(plan):
    counts = defaultdict(int)
    for step in plan["steps"]:
        counts[step["step"]] += 1
    return {"arm": plan["arm"], "setting": plan["setting"], "steps": dict(counts),
            "warnings": len(plan["warnings"])}


def fixture():
    """Original synthetic record in the MemOps schema (no upstream content)."""
    def turns(*lines):
        return [{"role": "user" if i % 2 == 0 else "assistant", "content": t} for i, t in enumerate(lines)]
    span = lambda s, t, q: {"segment_index": s, "turn_index": t, "quote": q}  # noqa: E731
    seg1 = turns("I live in Lisbon these days.", "Noted.", "My dog is called Biscuit.", "Sweet name.")
    seg2 = turns("I moved to Porto last month.", "Congrats.", "Please forget my dog's name.", "Done.",
                 "Maybe I will move to Faro next year.", "Sounds open.")
    op = lambda i, kind, valid, s, t, target, old, new, ev=None: {  # noqa: E731
        "operation_id": f"op{i}", "type": kind, "validity": valid,
        "trigger_span": span(s, t, ""), "target": {"target_id": target, "target_name": target},
        "old_value": old, "new_value": new, "evidence_spans": ev or [span(s, t, "")]}
    question = lambda pid, probe, setting, text, inc, exc: {  # noqa: E731
        "question_pair_id": pid, "evaluation_setting": setting, "evaluation_type": probe,
        "question": text, "expected_answer": "gold", "judge_rubric": {"must_include": inc, "must_not_include": exc},
        "diagnostic_checks": {"stale_value": "Lisbon" if exc else None}}
    answers = [question(f"p{i}_{probe.lower()}", probe, setting, text, inc, exc)
               for setting in SETTINGS for i, (probe, text, inc, exc) in enumerate((
                   ("StateTransition", "Where do I live now?", ["Porto"], ["Lisbon"]),
                   ("OperationApplication", "Fill in my dog's name on the form.", [], ["Biscuit"]),
                   ("TargetBinding", "Which city did I mention?", ["Porto"], [])))]
    return {"target_fact": "city of residence", "operation_type": "Update", "difficulty_knobs": {},
            "conversations": [{"segment_index": 1, "dialogue": seg1}, {"segment_index": 2, "dialogue": seg2}],
            "operations": [
                op(1, "remember", "confirmed", 1, 1, "city", None, "Lisbon"),
                op(2, "remember", "confirmed", 1, 3, "dog", None, "Biscuit"),
                op(3, "update", "confirmed", 2, 1, "city", "Lisbon", "Porto"),
                op(4, "forget", "confirmed", 2, 3, "dog", "Biscuit", None),
                op(5, "update", "tentative", 2, 5, "city", "Porto", "Faro"),
                op(6, "reflect", "confirmed", 2, 1, "habit", None, "Moves cities often",
                   [span(1, 1, ""), span(2, 1, "")])],
            "answer": answers}


def fixture_injected(evidence):
    """Synthetic injected record: each evidence segment spliced into a carrier."""
    carriers = [[{"role": "user", "content": f"carrier {c} turn {t}"} if t % 2 == 0 else
                 {"role": "assistant", "content": "ok"} for t in range(4)] for c in range(3)]
    inserts = []
    for seg, ci in ((1, 1), (2, 3)):
        dialogue = evidence["conversations"][seg - 1]["dialogue"]
        carriers[ci - 1][2:2] = copy.deepcopy(dialogue)
        inserts.append({"conversation_index": ci, "evidence_segment_index": seg,
                        "insertion_index": 2, "evidence_message_count": len(dialogue)})
    return {"conversations": [{"dialogue": d} for d in carriers],
            "injection_metadata": {"insertions": inserts}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--memops-dir", help="pinned MemOps checkout; default is the synthetic fixture")
    parser.add_argument("--run-tag", default="offline")
    parser.add_argument("--limit", type=int, default=5, help="evidence files to plan (default 5)")
    parser.add_argument("--out", help="write the report here instead of stdout")
    args = parser.parse_args(argv)
    summaries = []
    if args.memops_dir:
        verify_pin(args.memops_dir)
        root = Path(args.memops_dir) / "generated_result"
        evidence_files = sorted((root / "2-evidence_conversation").glob("*.json"))[:args.limit]
        pairs = [(p.stem, json.loads(p.read_text()), json.loads(
            (root / "4-inject_evidence_with_distractors" / p.name).read_text())) for p in evidence_files]
    else:
        record = fixture()
        pairs = [("fixture", record, fixture_injected(record))]
    for rid, record, injected in pairs:
        for setting in SETTINGS:
            for arm in ARMS:
                plan = ingest_plan(record, setting=setting, arm=arm, run_tag=args.run_tag,
                                   record_id=rid, injected=injected)
                summaries.append({"record": rid, **summarize(plan)})
    text = json.dumps(build_report(summaries), indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
