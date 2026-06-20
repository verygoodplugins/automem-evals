#!/usr/bin/env python3
"""Aggregate AMB `omb` result JSONs into the accuracy±CI / latency / tokens triplet.

Reads the fork's outputs/ dir. Most datasets are a single full-split run
(`automem`); at n=400-1540 the within-run 95% CI (1.96·sd/√n over per-question
scores) is already tighter than run-to-run judge noise, so ×1 is sufficient.
beam-100k is run ×3 (automem-rep1/2/3) as an explicit reproducibility check —
reported with the empirical across-run spread too.

Usage:  python3 runners/amb_aggregate.py [--outputs DIR]
"""
import argparse
import json
import math
import statistics
from pathlib import Path

DEFAULT_OUT = Path("/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs")

# Single full-split runs (run_name "automem-sub"): within-run CI.
RUN = "automem-sub"
SINGLE = [("locomo", "locomo10"), ("longmemeval", "s"), ("personamem", "32k"),
          ("beam", "500k"), ("beam", "1m"), ("beam", "10m")]
# Reproducibility check: 3 repeats.
REPRO = [("beam", "100k", ["automem-sub-rep1", "automem-sub-rep2", "automem-sub-rep3"])]


def load(out: Path, ds: str, run: str, split: str):
    p = out / ds / run / "rag" / f"{split}.json"
    return json.loads(p.read_text()) if p.exists() else None


def per_q_scores(d: dict) -> list[float]:
    """Per-question score in [0,1]: continuous `score` if present, else 0/1 correctness."""
    vals = []
    for r in d.get("results", []):
        s = r.get("score")
        vals.append(float(s) if s is not None else (1.0 if r.get("correct") else 0.0))
    return vals


def within_run_ci(d: dict) -> tuple[float, float, int]:
    vals = per_q_scores(d)
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan"), 0
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    ci = 1.96 * sd / math.sqrt(n)
    return mean, ci, n


def latency_tokens(d: dict) -> tuple[float, float]:
    return d.get("avg_retrieve_time_ms") or float("nan"), d.get("avg_context_tokens") or float("nan")


def row_single(out: Path, ds: str, split: str) -> str:
    d = load(out, ds, RUN, split)
    if not d:
        return f"| {ds}/{split} | **MISSING** | — | — |"
    mean, ci, n = within_run_ci(d)
    ret, tok = latency_tokens(d)
    return f"| {ds}/{split} | {mean*100:.1f}% ± {ci*100:.1f} (n={n}) | {ret:.0f} ms | {tok:.0f} |"


def row_repro(out: Path, ds: str, split: str, runs: list[str]) -> str:
    ds_runs = [d for d in (load(out, ds, r, split) for r in runs) if d]
    if not ds_runs:
        return f"| {ds}/{split} (×{len(runs)}) | **MISSING** | — | — |"
    accs = [d["accuracy"] for d in ds_runs]
    mean = statistics.mean(accs)
    spread = (max(accs) - min(accs)) if len(accs) > 1 else 0.0
    rets = [d["avg_retrieve_time_ms"] for d in ds_runs if d.get("avg_retrieve_time_ms")]
    toks = [d["avg_context_tokens"] for d in ds_runs if d.get("avg_context_tokens")]
    ret = statistics.median(rets) if rets else float("nan")
    tok = statistics.median(toks) if toks else float("nan")
    return (f"| {ds}/{split} (×{len(ds_runs)} repro) | {mean*100:.1f}% "
            f"(spread {spread*100:.1f}pp) | {ret:.0f} ms | {tok:.0f} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    rows = ["| Dataset | Accuracy (95% CI) | Recall latency (median) | Context tokens (median) |",
            "|---|---|---|---|"]
    for ds, split in SINGLE:
        rows.append(row_single(args.outputs, ds, split))
    for ds, split, runs in REPRO:
        rows.append(row_repro(args.outputs, ds, split, runs))
    print("\n".join(rows))


if __name__ == "__main__":
    main()
