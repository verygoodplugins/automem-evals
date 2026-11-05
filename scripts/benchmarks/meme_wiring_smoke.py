#!/usr/bin/env python3
"""Deterministic MEME wiring smoke and reporting-contract validator.

Offline: no network, no model calls, no AutoMem calls. A passing report shows the
pinned release matches the data contract the adapter and scoring rely on. It is
never an AutoMem score and carries no accuracy. See docs/eval/meme.md.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

PIN = {
    "hf_repo": "meme-benchmark/MEME",
    "hf_revision": "e14c4e685772014deb96f91dc7eddfbeb21d90d8",
    "file": "meme_filler32k.json",
    "sha256": "a88d28374a002b3e5b1683fb7201d06a1ce739d2ebf94c971c37bb65cf6ebdd3",
    "bytes": 20177963,
    "code_repo": "SeokwonJung-Jay/MEME-public",
    "code_commit": "a4f10db14ca14edd698374fa79ad6e1cfd1caf28",
}
TASKS = ("ER", "Agg", "Tr", "Del", "Cas", "Abs")
TRIVIAL_PASS_TASKS = ("Cas", "Abs", "Del")
PASS_TYPES = ("real_pass", "trivial_pass", "knew_but_failed", "never_knew")
HOP_TASKS = ("Cas", "Abs")
CONFIG_KEYS = ("limit", "current_only", "expansion", "enrichment")
OBJECT_KEYS = ("dataset", "answerer", "judge", "internal_llm", "cost_usd", "tasks", "overall")
# Post-change questions per episode (min, max), measured on the pinned file: one each for
# ER/Agg/Tr/Del, one or two for Cas/Abs. Bounds a subset's denominators.
PER_EPISODE = {"ER": (1, 1), "Agg": (1, 1), "Tr": (1, 1), "Del": (1, 1), "Cas": (1, 2), "Abs": (1, 2)}
EXPECTED = {
    "episodes": 100,
    "episodes_by_domain": {"personal_life": 50, "software_project": 50},
    "post_change_questions": 694,
    "post_change_by_domain": {"personal_life": 332, "software_project": 362},
    "post_change_by_task": {"ER": 100, "Agg": 100, "Tr": 100, "Del": 100, "Cas": 164, "Abs": 130},
    "pre_change_by_task": {"ER": 100, "Cas": 164, "Abs": 130, "Del": 100},
    "hops": {"Cas": {"1": 100, "2": 64}, "Abs": {"1": 100, "2": 30}},
}
# The adapter may read only these session fields; `type` (evidence/filler) is a label.
ADAPTER_SESSION_FIELDS = ("session_id", "timestamp", "conversation")
PAPER_ANSWERER, PAPER_JUDGE = "gpt-4.1-mini", "gpt-4o"


def parse_time(text):  # weekday name is dropped: %a is locale dependent
    return datetime.strptime(re.sub(r"\s*\(\w+\)", "", text), "%Y/%m/%d %H:%M")


def adapter_view(session):
    return {key: session[key] for key in ADAPTER_SESSION_FIELDS}


def slot(question):
    return next(iter(question["entity_values"]))  # same key the upstream judge uses


def ingest_schedule(episode):
    """Session ids visible before each question block; later sessions never leak earlier."""
    ids = [s["session_id"] for s in episode["sessions"]]
    before = episode["before_questions"]["position_after_session"]
    after = episode["after_questions"]["position_after_session"]
    return {"before": ids[: before + 1], "between": ids[before + 1: after + 1]}


def episode_errors(ep):
    eid, sessions, errors = ep["episode_id"], ep["sessions"], []
    stamps = [parse_time(s["timestamp"]) for s in sessions]
    ids = [s["session_id"] for s in sessions]
    if ep["total_sessions"] != len(sessions):
        errors.append(f"{eid}: total_sessions != len(sessions)")
    if len(set(ids)) != len(ids):
        errors.append(f"{eid}: duplicate session ids")
    if stamps != sorted(stamps):
        errors.append(f"{eid}: session timestamps are not chronological")
    positions = []
    for block in ("before_questions", "after_questions"):
        pos, when = ep[block]["position_after_session"], parse_time(ep[block]["timestamp"])
        positions.append(pos)
        if not 0 <= pos < len(sessions):
            errors.append(f"{eid}: {block} position {pos} out of range")
        elif when < stamps[pos] or (pos + 1 < len(sessions) and when >= stamps[pos + 1]):
            errors.append(f"{eid}: {block} time is outside the window after session index {pos}")
    if positions[0] >= positions[1]:
        errors.append(f"{eid}: before-questions must precede after-questions")
    before_slots = {slot(q) for q in ep["before_questions"]["questions"]}
    for q in ep["after_questions"]["questions"]:
        if q["task_type"] in TRIVIAL_PASS_TASKS and slot(q) not in before_slots:
            errors.append(f"{eid}: {q['task_type']} {slot(q)} has no before-question (trivial-pass)")
    return errors


def summarize(episodes):
    post, pre = Counter(), Counter()
    hops = {"Cas": Counter(), "Abs": Counter()}
    domains, post_domains = Counter(), Counter()
    for ep in episodes:
        domains[ep["domain"]] += 1
        for q in ep["after_questions"]["questions"]:
            post[q["task_type"]] += 1
            post_domains[ep["domain"]] += 1
            if q["task_type"] in hops:
                hops[q["task_type"]][str(q.get("hop"))] += 1
        pre.update(q["task_type"] for q in ep["before_questions"]["questions"])
    return {"episodes": len(episodes), "episodes_by_domain": dict(domains),
            "post_change_questions": sum(post.values()), "post_change_by_domain": dict(post_domains),
            "post_change_by_task": dict(post), "pre_change_by_task": dict(pre),
            "hops": {task: dict(counts) for task, counts in hops.items()}}


def canonical(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def smoke(path, pin=PIN, expected=EXPECTED):
    raw = Path(path).read_bytes()
    digest, errors = hashlib.sha256(raw).hexdigest(), []
    if pin and (digest != pin["sha256"] or len(raw) != pin["bytes"]):
        errors.append(f"dataset bytes/sha256 do not match the pin ({len(raw)}, {digest})")
    episodes = json.loads(raw)
    summary = summarize(episodes)
    errors += [f"{key}: {summary[key]} != expected {want}" for key, want in expected.items() if summary[key] != want]
    schedules = []
    for ep in episodes:
        problems = episode_errors(ep)
        errors += problems
        if not problems:
            schedules.append(ingest_schedule(ep))
    report = {
        "kind": "meme-wiring-smoke", "status": "failed" if errors else "ok", "errors": errors,
        "pin": pin, "dataset_sha256": digest, "summary": summary,
        "schedule": {"sessions_before_pre_change_questions": sum(len(s["before"]) for s in schedules),
                     "sessions_between_question_blocks": sum(len(s["between"]) for s in schedules)},
        "adapter_session_fields": list(ADAPTER_SESSION_FIELDS),
        "model_calls": 0, "network_calls": 0, "automem_calls": 0, "automem_score": None,
        "claim": "wiring only; no AutoMem score or paper-comparable result",
    }
    report["report_sha256"] = hashlib.sha256(canonical(report).encode()).hexdigest()
    return report


def is_count(value, minimum=0):  # bool is an int subclass but never a count
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def obj(value):  # malformed nesting must surface as validation errors, never as a traceback
    return value if isinstance(value, dict) else {}


def disclosure_errors(result):
    """Executed-run disclosures from the reporting contract in docs/eval/meme.md."""
    errors = []
    if "embedding_model" not in result:
        errors.append("embedding_model must be disclosed (null only when none is used)")
    if not isinstance(result.get("arm"), str) or not result["arm"]:
        errors.append("arm must be disclosed")
    if result.get("maturation") not in ("cold", "matured"):
        errors.append("maturation must be 'cold' or 'matured'")
    automem = obj(result.get("automem"))
    if not isinstance(automem.get("commit"), str) or not automem["commit"]:
        errors.append("automem.commit must be disclosed")
    errors += [f"automem.config.{key} must be disclosed" for key in CONFIG_KEYS if key not in obj(automem.get("config"))]
    errors += [f"usage.{key} must be a non-negative integer" for key in ("tokens", "calls")
               if not is_count(obj(result.get("usage")).get(key))]
    if not isinstance(result["dataset"].get("hf_revision"), str) or not result["dataset"]["hf_revision"]:
        errors.append("dataset.hf_revision must be disclosed")
    return errors


def hop_errors(task, row, episodes, full, expected):
    hops, parts = obj(row.get("hops")), [obj(obj(row.get("hops")).get(h)) for h in ("1", "2")]
    sound = set(hops) == {"1", "2"} and all(is_count(p.get("n")) and is_count(p.get("correct"))
                                           and p["correct"] <= p["n"] for p in parts)
    if not sound or sum(p["n"] for p in parts) != row["n"] or sum(p["correct"] for p in parts) != row["correct"]:
        return [f"tasks.{task}.hops needs '1' and '2' splits of integer correct <= n that sum to the task row"]
    if episodes is None:
        return []
    (first, second), cap = (p["n"] for p in parts), expected["hops"][task]
    if full and (first, second) != (cap["1"], cap["2"]):
        return [f"tasks.{task}.hops n must be {cap} on a full run"]
    # Pinned file: every episode has exactly one hop-1 and zero or one hop-2 question, so leaving
    # out `omitted` episodes removes at most `omitted` hop-2 questions from the full count.
    if not full:
        least, most = max(0, cap["2"] - (expected["episodes"] - episodes)), min(episodes, cap["2"])
        if first != episodes or not least <= second <= most:
            return [f"tasks.{task}.hops n: a {episodes}-episode subset has {episodes} hop-1 and "
                    f"{least}-{most} hop-2 questions"]
    return []


def contract_errors(result, expected=EXPECTED):
    """Validate a result file against the reporting contract; [] means publishable shape."""
    status = result.get("run_status")
    if status not in ("executed", "wiring_only"):
        return ["run_status must be 'executed' or 'wiring_only'"]
    errors = [f"missing {key}" for key in ("system",) + OBJECT_KEYS if key not in result]
    errors += [f"{key} must be an object" for key in OBJECT_KEYS if key in result and not isinstance(result[key], dict)]
    if errors:
        return errors
    tasks = result["tasks"]
    if status == "wiring_only":
        scored = [t for t in TASKS if obj(tasks.get(t)).get("accuracy") is not None]
        return [f"wiring_only result must not carry accuracy: {scored}"] if scored or result["overall"].get("macro_mean") is not None else []
    errors = disclosure_errors(result)
    for key in ("answerer", "judge"):
        if not isinstance(result[key].get("model"), str) or not result[key]["model"]:
            errors.append(f"{key}.model must be disclosed")
    if "model" not in result["internal_llm"]:
        errors.append("internal_llm.model must be disclosed (null only when none is used)")
    for key in ("ingest_per_episode", "inference_per_episode", "judge_total"):
        value = result["cost_usd"].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f"cost_usd.{key} must be a non-negative number")
    episodes, subset = result["dataset"].get("episodes"), result["dataset"].get("subset")
    if not is_count(episodes, 1) or episodes > expected["episodes"]:
        errors.append(f"dataset.episodes must be an integer from 1 to {expected['episodes']}")
        episodes = None
    full = episodes == expected["episodes"]
    if not isinstance(subset, bool) or (episodes is not None and subset == full):
        errors.append(f"dataset.subset must be a boolean that is true exactly when episodes < {expected['episodes']}")
    accuracies = []
    for task in TASKS:
        row = obj(tasks.get(task))
        n, correct = row.get("n"), row.get("correct")
        if not (is_count(n, 1) and is_count(correct) and correct <= n):
            errors.append(f"tasks.{task} needs integer correct <= n, n > 0")
            continue
        full_n, per = expected["post_change_by_task"][task], PER_EPISODE[task]
        if episodes is not None:
            low, high = (full_n, full_n) if full else (episodes * per[0], min(episodes * per[1], full_n))
            if not low <= n <= high:
                scope = "full runs use" if full else f"a {episodes}-episode subset uses"
                errors.append(f"tasks.{task}.n={n}; {scope} {low if low == high else f'{low}-{high}'}")
        accuracy = row.get("accuracy")
        if isinstance(accuracy, bool) or accuracy != round(correct / n, 6):
            errors.append(f"tasks.{task}.accuracy must equal round(correct/n, 6)")
        else:
            accuracies.append(accuracy)
        if task in TRIVIAL_PASS_TASKS:
            kinds = obj(row.get("pass_types"))
            if not (all(is_count(kinds.get(k)) for k in PASS_TYPES)
                    and sum(kinds[k] for k in PASS_TYPES) == n and kinds["real_pass"] == correct):
                errors.append(f"tasks.{task}.pass_types must partition n into non-negative integers with real_pass == correct")
        if task in HOP_TASKS:
            errors += hop_errors(task, row, episodes, full, expected)
    if len(accuracies) == len(TASKS) and result["overall"].get("macro_mean") != round(sum(accuracies) / len(TASKS), 6):
        errors.append("overall.macro_mean must be the unweighted mean of the six task accuracies")
    comparable = (result["answerer"].get("model") == PAPER_ANSWERER and result["judge"].get("model") == PAPER_JUDGE
                  and full and result["dataset"].get("hf_revision") == PIN["hf_revision"])
    if bool(result.get("paper_comparable")) != comparable:
        errors.append(f"paper_comparable must be {comparable} for this answerer/judge/dataset")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dataset", type=Path, help="pinned meme_filler32k.json")
    mode.add_argument("--check-contract", type=Path, help="scored-run result JSON to validate")
    parser.add_argument("--output", type=Path, help="write the deterministic smoke report here")
    args = parser.parse_args(argv)
    if args.check_contract:
        errors = contract_errors(json.loads(args.check_contract.read_text(encoding="utf-8")))
        print(canonical({"contract_errors": errors}), end="")
        return 1 if errors else 0
    report = smoke(args.dataset)
    text = canonical(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
