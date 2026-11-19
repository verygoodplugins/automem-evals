#!/usr/bin/env python3
"""Project an all-or-none client gate onto saved zero-floor recall results.

No stored result lists or question identifiers are copied into the output.
This does not simulate per-result server filtering or re-running recall.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

BASELINE = "1a7ba1a6afe69835f62ad7f6013e33301d1ab83e"
CANDIDATE = "4431d20e93ee194ed0749d91934af0219fad7b4f"
FIXTURE = "d89af992a8e71bc2aafde8ba54fdb441e93b6b716de63bc9cc1a57b0b64559f6"
KINDS = {"identifier": 16, "paraphrase": 16, "negative": 16, "wrong_scope": 4}
THRESHOLDS = (0.0, 0.25, 0.30, 0.35, 0.38, 0.40, 0.45, 0.50)


def load_rows(path, arm):
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    if doc.get("baseline_sha") != BASELINE or doc.get("fixture_sha256") != FIXTURE:
        raise ValueError(
            "baseline or fixture revision does not match the frozen experiment"
        )
    if doc.get("mode") != arm or (
        arm == "candidate" and doc.get("candidate_sha") != CANDIDATE
    ):
        raise ValueError(
            "candidate or arm revision does not match the frozen experiment"
        )
    rows = {}
    for row in doc["result"]["evaluation"]["rows"]:
        if row["kind"] not in KINDS or row["floor"] not in (0, 0.4):
            continue
        key = (row["kind"], row["query_id"], float(row["floor"]))
        if key in rows:
            raise ValueError("duplicate query/floor row")
        score, count, rank = row["top_score"], row["count"], row["any_rank"]
        if (
            not isinstance(count, int)
            or count < 0
            or bool(count) != (score is not None)
        ):
            raise ValueError("invalid result count or missing top score")
        if score is not None and (
            not isinstance(score, (int, float)) or not math.isfinite(score)
        ):
            raise ValueError("invalid top score")
        if rank is not None and (not isinstance(rank, int) or not 1 <= rank <= count):
            raise ValueError("invalid target rank")
        rows[key] = row
    for kind, expected_count in KINDS.items():
        zero = {key[1] for key in rows if key[0] == kind and key[2] == 0.0}
        fixed = {key[1] for key in rows if key[0] == kind and key[2] == 0.4}
        if len(zero) != expected_count or zero != fixed:
            raise ValueError(f"missing or mismatched zero/0.4 rows for {kind}")
    return rows, hashlib.sha256(raw).hexdigest()


def counts(rows):
    """Count observable outcomes without including query IDs or result text."""
    result = {
        "queries": len(rows),
        "nonempty": 0,
        "target_at_1": 0,
        "target_at_5": 0,
        "cross_scope_queries": 0,
        "inactive_leak_queries": 0,
    }
    for row in rows:
        result["nonempty"] += row["count"] > 0
        rank = row["any_rank"]
        result["target_at_1"] += rank == 1
        result["target_at_5"] += rank is not None and rank <= 5
        result["cross_scope_queries"] += bool(row["scope_leaks"])
        result["inactive_leak_queries"] += bool(row["inactive_leaks"])
    result["nonempty_rate"] = result["nonempty"] / len(rows) if rows else None
    return result


def gate(rows, threshold):
    """Keep the entire saved list or abstain, based only on its top score."""
    selected = [
        row
        for row in rows
        if row["top_score"] is not None and row["top_score"] >= threshold
    ]
    summary = counts(selected)
    summary["queries"] = len(rows)
    summary["abstained"] = len(rows) - len(selected)
    summary["nonempty_rate"] = summary["nonempty"] / len(rows) if rows else None
    return summary


def analyze(baseline, candidate):
    if baseline.keys() != candidate.keys():
        raise ValueError("arms do not contain the same query/floor rows")
    if any(baseline[key]["expected"] != candidate[key]["expected"] for key in baseline):
        raise ValueError("arms have different expected targets")
    output = {"arms": {}, "thresholds": list(THRESHOLDS)}
    for name, source in (("baseline", baseline), ("candidate", candidate)):
        arm = {
            "projected_query_gate": {},
            "observed_server_floor_0_4": {},
            "gate_vs_server_0_4_disagreements": {},
        }
        for kind in KINDS:
            zero = [
                row
                for (k, _qid, floor), row in source.items()
                if k == kind and floor == 0.0
            ]
            fixed = [
                row
                for (k, _qid, floor), row in source.items()
                if k == kind and floor == 0.4
            ]
            arm["observed_server_floor_0_4"][kind] = counts(fixed)
            discrepancies = {"nonempty": 0, "target_at_1": 0, "target_at_5": 0}
            for row in zero:
                actual = source[(kind, row["query_id"], 0.4)]
                keep = row["top_score"] is not None and row["top_score"] >= 0.4
                rank = row["any_rank"] if keep else None
                actual_rank = actual["any_rank"]
                discrepancies["nonempty"] += keep != (actual["count"] > 0)
                discrepancies["target_at_1"] += (rank == 1) != (actual_rank == 1)
                discrepancies["target_at_5"] += (rank is not None and rank <= 5) != (
                    actual_rank is not None and actual_rank <= 5
                )
            arm["gate_vs_server_0_4_disagreements"][kind] = discrepancies
            for threshold in THRESHOLDS:
                arm["projected_query_gate"].setdefault(f"{threshold:.2f}", {})[kind] = (
                    gate(zero, threshold)
                )
        output["arms"][name] = arm
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", required=True, help="local strict baseline receipt"
    )
    parser.add_argument(
        "--candidate", required=True, help="local strict candidate receipt"
    )
    parser.add_argument("--output", required=True, help="new aggregate JSON path")
    args = parser.parse_args()
    baseline, baseline_hash = load_rows(args.baseline, "baseline")
    candidate, candidate_hash = load_rows(args.candidate, "candidate")
    doc = {
        "kind": "exploratory-client-top-score-gate",
        "baseline_revision": BASELINE,
        "candidate_revision": CANDIDATE,
        "fixture_sha256": FIXTURE,
        "input_sha256": {"baseline": baseline_hash, "candidate": candidate_hash},
        "limitations": [
            "Previously examined synthetic examples; no untouched holdout and no threshold selected.",
            "Client gate retains or rejects the entire saved zero-floor result list; it does not simulate per-result server filtering or recall re-ranking.",
            "Only original query-level top scores are saved; individual lower-ranked scores are unavailable.",
            "Target retention is an upper bound only for per-item filtering of the same saved list, not for a fresh server request that can change candidates.",
            "0.4 server results are separate live observations and may differ from the post-hoc gate.",
            "Negative controls are labelled as no-answer; nonempty results measure evidence returned, not agent answer correctness.",
        ],
        **analyze(baseline, candidate),
    }
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(doc, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
