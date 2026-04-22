#!/usr/bin/env python3
"""Same idea as extract_v1_subset.py but for V2 Phase 3 results."""
from __future__ import annotations

import argparse
import json
import pathlib


def _parse_conv_spec(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(part))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Source BEAM results JSON")
    ap.add_argument("--convs", required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    keep = _parse_conv_spec(args.convs)
    with open(args.src) as f:
        data = json.load(f)

    filtered = [ev for ev in data["evaluations"] if ev["conversation_idx"] in keep]

    from collections import defaultdict
    by_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "scores": []})
    for ev in filtered:
        cutoff = ev["cutoff_results"]["top_100"]
        cat = ev["question_type"]
        by_cat[cat]["total"] += 1
        by_cat[cat]["correct"] += 1 if cutoff["judgment"] == "PASS" else 0
        by_cat[cat]["scores"].append(cutoff["score"])

    overall_total = sum(d["total"] for d in by_cat.values())
    overall_correct = sum(d["correct"] for d in by_cat.values())
    all_scores = [s for d in by_cat.values() for s in d["scores"]]

    metrics = {
        "top_100": {
            "overall": {
                "total": overall_total,
                "correct": overall_correct,
                "errors": 0,
                "accuracy": 100.0 * overall_correct / overall_total if overall_total else 0.0,
                "avg_score": sum(all_scores) / len(all_scores) if all_scores else 0.0,
            },
            "by_question_type": {
                cat: {
                    "total": d["total"],
                    "correct": d["correct"],
                    "accuracy": 100.0 * d["correct"] / d["total"] if d["total"] else 0.0,
                    "avg_score": sum(d["scores"]) / d["total"] if d["total"] else 0.0,
                }
                for cat, d in by_cat.items()
            },
        }
    }

    out_data = {
        "metadata": {**data["metadata"], "conversations": args.convs, "total_questions": overall_total,
                     "_subset_note": f"filtered from {args.src}"},
        "metrics_by_cutoff": metrics,
        "evaluations": filtered,
    }

    args.out.write_text(json.dumps(out_data))
    size_mb = args.out.stat().st_size / (1024 * 1024)
    print(f"wrote {args.out}  ({overall_total} questions, {size_mb:.1f} MB)")
    print(f"pass_rate={100.0 * overall_correct / overall_total:.2f}%  avg_score={sum(all_scores)/len(all_scores):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
