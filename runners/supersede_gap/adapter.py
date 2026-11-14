"""Supersede (arXiv:2606.27472) offline scaffold for AutoMem.

Scaffold only: no network, no model calls, no AutoMem calls, and no upstream code
or data vendored. The CLI has no recall transport, so every report it can emit is
``not_scored`` (rates null). ``aggregate`` is the scoring contract a future live
runner must use; it still refuses to score unless every scorable question has a
verdict. Pins, mapping and acceptance criteria: issue #105 and
docs/eval/supersede.md. Paper numbers are baselines on a different construct and
are never AutoMem scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ARXIV_ID = "2606.27472"
UPSTREAM_REPO = "https://github.com/Vrin-cloud/supersede"
UPSTREAM_COMMIT = "677993d3713c265329ac935262d3c08cbfa4cd63"  # main, 2026-06-30
UPSTREAM_LICENSE = "Apache-2.0"
DATASET_REPO = "xiaowu0162/longmemeval-cleaned"  # MIT; upstream's env fetches it unpinned
DATASET_REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
DATASET_FILE = "longmemeval_oracle.json"
DATASET_SHA256 = "821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c"
QUESTION_TYPE = "knowledge-update"
# Measured on the pinned file: strata are decided by the (earlier, later) has_answer turn counts.
EXPECTED = {"questions": 78, "strata": {"both_labeled": 70, "late_only": 2, "abstention": 6}}
VARIANTS = ("plain", "supersede_oracle")
CLASSES = ("current", "stale", "other")
RECALL_LIMIT = 10
RELATION = "INVALIDATED_BY"  # old -> new; EVOLVED_INTO is the evolution alternative
MATURED_REASON = "maturation-v1 is not wired (narrative-clock /consolidate dependency); docs/eval/maturation.md"
PAPER_BASELINES = {
    "label": "paper-reported (bounded 300-char notes reader, n=78 oracle); never AutoMem scores",
    "rows": [
        {"reader": "gpt-4.1-mini", "full_context": 0.82, "bounded_memory": 0.63},
        {"reader": "gpt-4.1", "full_context": 0.91, "bounded_memory": 0.64},
        {"reader": "gpt-5.4", "full_context": 0.92, "bounded_memory": 0.77},
    ],
}
_SAFE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class PinError(RuntimeError):
    """The dataset is not the pinned file; nothing downstream may run."""


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    evidence: bool = field(repr=False)  # scoring/oracle label only; never reaches a write payload


@dataclass(frozen=True)
class Session:
    session_id: str
    started: datetime
    turns: tuple[Turn, ...]


@dataclass(frozen=True)
class Task:
    question_id: str
    question: str
    gold: str
    asked: datetime
    sessions: tuple[Session, ...]

    @property
    def stratum(self) -> str:
        if self.question_id.endswith("_abs"):
            return "abstention"
        early, late = (sum(t.evidence for t in s.turns) for s in (self.sessions[0], self.sessions[-1]))
        return "both_labeled" if early and late else "late_only" if late else "unlabeled"

    @property
    def scorable(self) -> bool:
        return self.stratum != "abstention"


def parse_time(text: str) -> datetime:  # the weekday name is dropped: %a is locale dependent
    return datetime.strptime(re.sub(r"\s*\(\w+\)", "", text), "%Y/%m/%d %H:%M")


def iso(moment: datetime) -> str:  # dataset clocks carry no zone; treated as UTC narrative time
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_tasks(path: Path, *, expected_sha256: str | None = None, expected: dict | None = None) -> list[Task]:
    raw = Path(path).read_bytes()
    want = DATASET_SHA256 if expected_sha256 is None else expected_sha256
    if hashlib.sha256(raw).hexdigest() != want:
        raise PinError(f"{path} is not the pinned {DATASET_FILE} (sha256 != {want})")
    tasks = []
    for item in json.loads(raw):
        if item.get("question_type") != QUESTION_TYPE:
            continue
        sessions = tuple(
            Session(sid, parse_time(date), tuple(Turn(t["role"], t["content"], bool(t.get("has_answer"))) for t in turns))
            for sid, date, turns in zip(item["haystack_session_ids"], item["haystack_dates"], item["haystack_sessions"])
        )
        stamps = [s.started for s in sessions]
        if len(sessions) != 2 or any(a >= b for a, b in zip(stamps, stamps[1:])):
            raise PinError(f"{item['question_id']}: expected two strictly chronological sessions")
        asked = parse_time(item["question_date"])
        tasks.append(Task(item["question_id"], item["question"], str(item["answer"]), asked, sessions))
    target = EXPECTED if expected is None else expected
    got = {"questions": len(tasks), "strata": dict(Counter(t.stratum for t in tasks))}
    if got != target:
        raise PinError(f"dataset shape {got} != pinned {target}")
    return tasks


def question_tag(run_id: str, question_id: str) -> str:
    """Isolated per-question tag. Lowercase only: AutoMem lowercases stored tags."""
    parts = (run_id, question_id.lower())
    if not all(_SAFE.match(p) for p in parts):
        raise ValueError(f"run_id and question_id must match {_SAFE.pattern}: {parts!r}")
    return "supersede:" + ":".join(parts)


def _key(task: Task, session: int, turn: int) -> str:
    return f"{task.question_id}:s{session}:t{turn}"


def evidence_keys(task: Task) -> tuple[set[str], set[str]]:
    """(stale, current): flagged turns of the earlier and the later session. Scoring side only."""
    last = len(task.sessions) - 1
    if not task.scorable:
        return set(), set()
    flagged = lambda i: {_key(task, i, j) for j, t in enumerate(task.sessions[i].turns) if t.evidence}  # noqa: E731
    return flagged(0), flagged(last)


def build_plan(task: Task, run_id: str, variant: str) -> dict[str, Any]:
    """Deterministic writes, optional lifecycle links and one probe for a question.

    Writes carry content, tags, a narrative ``timestamp`` (-> ``t_valid``, +1s per turn for a total
    order) and neutral metadata. The ``has_answer`` label never enters a payload. ``supersede_oracle``
    links earlier to later evidence *using those labels*: an upper bound for the read path, not
    a measure of AutoMem detecting revisions.
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}: {variant!r}")
    tag = question_tag(run_id, task.question_id)
    writes, stamps = [], {}
    for i, session in enumerate(task.sessions):
        for j, turn in enumerate(session.turns):
            key = _key(task, i, j)
            stamps[key] = iso(session.started + timedelta(seconds=j))
            writes.append({
                "key": key, "content": f"{turn.role}: {turn.content}", "tags": [tag], "timestamp": stamps[key],
                "metadata": {"question_id": task.question_id, "session_id": session.session_id,
                             "turn_index": j, "role": turn.role},
            })
    stale, current = evidence_keys(task)
    links = []
    if variant == "supersede_oracle":
        links = [{"old": o, "new": n, "at": stamps[n], "relation": RELATION} for n in sorted(current) for o in sorted(stale)]
    # Read params are identical across variants so the write path is the only experimental variable.
    probe = {"query": task.question, "tags": [tag], "tag_mode": "all", "tag_match": "exact",
             "limit": RECALL_LIMIT, "current_only": True, "end": iso(task.asked)}
    return {"question_id": task.question_id, "stratum": task.stratum, "variant": variant, "tag": tag,
            "writes": writes, "links": links, "probe": probe}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text).lower())).strip()


def _mentions(text_norm: str, value: str) -> bool:
    v = normalize(value)
    return bool(v) and re.search(rf"(?<!\w){re.escape(v)}(?!\w)", text_norm) is not None


def _fold(current: bool, stale: bool) -> tuple[str, str | None]:
    if current != stale:
        return ("current", None) if current else ("stale", None)
    return ("other", "both" if current else "neither")


def classify_text(answer: str, gold: str, stale_values: Iterable[str]) -> dict[str, Any]:
    """Answer level. Stale values are not shipped by LongMemEval: they need a sidecar annotation."""
    a = normalize(answer)
    cls, detail = _fold(_mentions(a, gold), any(_mentions(a, s) for s in stale_values))
    return {"class": cls, "detail": detail}


def classify_recall(ranked_keys: list[str], stale: set[str], current: set[str]) -> dict[str, Any]:
    """Retrieval level: are the later (current) / earlier (stale) evidence turns in the recalled top-k."""
    first = lambda keys: next((i + 1 for i, k in enumerate(ranked_keys) if k in keys), None)  # noqa: E731
    cur, stl = first(current), first(stale)
    cls, detail = _fold(cur is not None, stl is not None)
    return {"class": cls, "detail": detail, "current_rank": cur, "stale_rank": stl}


def aggregate(tasks: list[Task], verdicts: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """Rates over scorable questions. Any missing verdict makes every rate null (``not_scored``)."""
    scorable = [t for t in tasks if t.scorable]
    missing = [t.question_id for t in scorable if t.question_id not in (verdicts or {})]
    reason = "no scorable questions" if not scorable else (
        f"{len(missing)} of {len(scorable)} scorable questions have no verdict" if missing else None)
    if reason:
        return {"status": "not_scored", "reason": reason, "n": len(scorable), "rates": None,
                "other_breakdown": None, "by_stratum": None}
    rows = [(t.stratum, verdicts[t.question_id]) for t in scorable]
    bad = {v["class"] for _, v in rows} - set(CLASSES)
    if bad:  # an unknown class would silently fall out of the rates
        raise ValueError(f"verdict classes must be in {CLASSES}: {sorted(bad)}")

    def rates(subset: list) -> dict[str, float]:
        return {c: sum(v["class"] == c for _, v in subset) / len(subset) for c in CLASSES}

    by_stratum = {}
    for name in sorted({stratum for stratum, _ in rows}):
        part = [r for r in rows if r[0] == name]
        by_stratum[name] = {"n": len(part), "rates": rates(part)}
    return {"status": "scored", "reason": None, "n": len(rows), "rates": rates(rows),
            "other_breakdown": dict(Counter(v["detail"] for _, v in rows if v["class"] == "other")),
            "by_stratum": by_stratum}


def build_report(tasks: list[Task], run_id: str, variants: Iterable[str] = VARIANTS,
                 verdicts: dict[str, dict[str, dict[str, Any]]] | None = None, subset: str = "full") -> dict[str, Any]:
    out = {}
    for v in variants:
        plans = [build_plan(t, run_id, v) for t in tasks]
        out[v] = {"uses_oracle_labels": v == "supersede_oracle",
                  "plan": {"questions": len(plans), "writes": sum(len(p["writes"]) for p in plans),
                           "links": sum(len(p["links"]) for p in plans)},
                  "cold": aggregate(tasks, (verdicts or {}).get(v)),
                  "matured": {"status": "not_run", "reason": MATURED_REASON}}
    scored = all(r["cold"]["status"] == "scored" for r in out.values())
    return {"benchmark": "supersede-gap", "arxiv": ARXIV_ID, "status": "scored" if scored else "not_scored",
            "paper_comparable": False, "maturation": "cold", "run_id": run_id, "subset": subset,
            "pin": {"code": UPSTREAM_REPO, "commit": UPSTREAM_COMMIT, "license": UPSTREAM_LICENSE,
                    "dataset": DATASET_REPO, "revision": DATASET_REVISION, "file": DATASET_FILE, "sha256": DATASET_SHA256},
            "dataset": {"questions": len(tasks), "strata": dict(Counter(t.stratum for t in tasks)),
                        "scorable": sum(t.scorable for t in tasks)},
            "variants": out, "paper_baselines": PAPER_BASELINES}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help=f"pinned {DATASET_FILE} (fetched by revision, never committed)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--variant", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    ap.add_argument("--limit", type=int, help="first N questions in file order; reported as a subset")
    ap.add_argument("--out", type=Path, help="write the report here instead of stdout")
    ap.add_argument("--plan-out", type=Path, help="write one JSON plan per question and variant (JSONL)")
    args = ap.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be at least 1")
    try:
        tasks = load_tasks(args.data)
    except PinError as exc:
        raise SystemExit(f"refusing to continue: {exc}") from exc
    subset = "full"
    if args.limit is not None:
        tasks, subset = tasks[: args.limit], f"first-{args.limit}"
    report = build_report(tasks, args.run_id, args.variant, subset=subset)
    if args.plan_out:
        args.plan_out.write_text("".join(json.dumps(build_plan(t, args.run_id, v)) + "\n" for v in args.variant for t in tasks))
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
