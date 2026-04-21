#!/usr/bin/env python3
"""
Compare recall-ruleset configurations by running the same scenarios under each.

Loads:
  - rulesets/*.json — recall parameter configs
  - scenarios/session_start_v1.json — queries + expected hits
  - data/seed_memories/corpus_v1.manifest.json — memory_id → scenario hits

Produces:
  - data/results/<timestamp>-comparison.md — a markdown report suitable for
    eyeballing plus raw per-scenario metrics.

Metrics per scenario per ruleset:
  - K (number of memories returned)
  - expected_hit_count (how many expected memories appeared)
  - expected_hit_rank_first (1-indexed rank of first expected hit, or None)
  - precision_at_5 (of top 5, fraction that are expected hits)
  - recall (expected hits recalled / total possible in corpus)
  - top_score (raw score of #1 result)

Usage:
  python3 runners/compare_rulesets.py \
      --endpoint http://localhost:8001 \
      --token test-token \
      --rulesets baseline_v1 bare_tag_1m_v2 \
      --scenarios session_start_v1
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent.parent
# MANIFEST is resolved at runtime from --manifest arg (default: corpus_v1.manifest.json)


def get_recall(endpoint: str, token: str, params: dict) -> dict:
    """Execute a /recall call. Params with None values are dropped; list values are repeated."""
    flat: list[tuple[str, str]] = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, list):
            for item in v:
                flat.append((k, str(item)))
        elif isinstance(v, bool):
            flat.append((k, "true" if v else "false"))
        else:
            flat.append((k, str(v)))
    qs = urllib.parse.urlencode(flat)
    req = urllib.request.Request(
        f"{endpoint}/recall?{qs}",
        headers={"X-Api-Key": token},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def run_phase(
    endpoint: str,
    token: str,
    ruleset: dict,
    phase: int,
    scenario: dict,
) -> dict:
    """Given a ruleset + scenario, construct the recall params and execute."""
    phase_key = {1: "phase_1_preferences", 2: "phase_2_task_context", 3: "phase_3_debugging"}[phase]
    cfg = ruleset[phase_key]
    params: dict = {}

    if phase == 1:
        params["tags"] = cfg["tags"]
        params["tag_match"] = cfg.get("tag_match", "exact")
        params["limit"] = cfg["limit"]
    elif phase == 2:
        q = scenario["query"]
        # Ruleset may suggest extra "queries_suffix" that widens the query set
        suffixes = cfg.get("queries_suffix", [])
        # Substitute <project> placeholder in suffixes
        proj = scenario.get("project_slug") or ""
        suffixes = [s.replace("<project>", proj) for s in suffixes if "<project>" not in s or proj]
        queries = [q] + suffixes if q else suffixes
        # /recall supports either `query` (single) or `queries` (array). Use queries.
        params["queries"] = queries
        if cfg.get("tags_from") == "project_slug" and scenario.get("project_slug"):
            params["tags"] = [scenario["project_slug"]]
            params["tag_match"] = "exact"
        if cfg.get("auto_decompose"):
            params["auto_decompose"] = True
        if cfg.get("time_query"):
            params["time_query"] = cfg["time_query"]
        params["limit"] = cfg["limit"]
        if cfg.get("expand_relations"):
            params["expand_relations"] = True
            if cfg.get("expand_min_strength") is not None:
                params["expand_min_strength"] = cfg["expand_min_strength"]
            if cfg.get("relation_limit") is not None:
                params["relation_limit"] = cfg["relation_limit"]
            if cfg.get("expansion_limit") is not None:
                params["expansion_limit"] = cfg["expansion_limit"]
    elif phase == 3:
        params["query"] = scenario["query"]
        params["tags"] = cfg["tags"]
        params["tag_match"] = cfg.get("tag_match", "exact")
        params["limit"] = cfg["limit"]
        if cfg.get("expand_relations"):
            params["expand_relations"] = True
            if cfg.get("expand_min_strength") is not None:
                params["expand_min_strength"] = cfg["expand_min_strength"]
            if cfg.get("relation_limit") is not None:
                params["relation_limit"] = cfg["relation_limit"]
            if cfg.get("expansion_limit") is not None:
                params["expansion_limit"] = cfg["expansion_limit"]

    resp = get_recall(endpoint, token, params)
    return {"params": params, "response": resp}


def score_scenario(
    result: dict,
    scenario: dict,
    manifest: dict,
    at_k: int = 5,
) -> dict:
    """Compute metrics for a single scenario run."""
    expected_tags = set(scenario["expected_hit_tags"])
    # Map: memory_id → set of scenario hit tags (from manifest)
    m2s = manifest["memory_to_scenarios"]
    # All memory_ids that should surface for this scenario
    expected_mids = set()
    for s in expected_tags:
        for mid in manifest["scenario_to_memories"].get(s, []):
            expected_mids.add(mid)

    results = result["response"].get("results", [])
    ranked_ids = []
    for r in results:
        mid = r.get("id") or r.get("memory", {}).get("id")
        if mid:
            ranked_ids.append(mid)

    # Precision@K
    topk = ranked_ids[:at_k]
    hits_in_topk = sum(1 for m in topk if m in expected_mids)
    precision_at_k = hits_in_topk / max(len(topk), 1) if topk else 0.0

    # Recall — of all expected memories in the corpus, how many appear in results
    hits_total = sum(1 for m in ranked_ids if m in expected_mids)
    recall = hits_total / max(len(expected_mids), 1) if expected_mids else 0.0

    # Rank of first hit
    rank_first = None
    for i, mid in enumerate(ranked_ids, start=1):
        if mid in expected_mids:
            rank_first = i
            break

    top_score = results[0].get("final_score") or results[0].get("score") if results else None

    return {
        "results_returned": len(results),
        "expected_in_corpus": len(expected_mids),
        "hits_total": hits_total,
        "hits_in_top_k": hits_in_topk,
        "precision_at_k": precision_at_k,
        "recall": recall,
        "rank_of_first_hit": rank_first,
        "top_score": top_score,
    }


def load_ruleset(name: str) -> dict:
    path = HERE / "rulesets" / f"{name}.json"
    return json.loads(path.read_text())


def load_scenarios(name: str) -> dict:
    path = HERE / "scenarios" / f"{name}.json"
    return json.loads(path.read_text())


def load_manifest(name: str) -> dict:
    return json.loads((HERE / "data" / "seed_memories" / name).read_text())


def format_report(
    ruleset_names: list[str],
    scenario_set: dict,
    results: dict,  # {(ruleset_name, scenario_id): {"run": {...}, "metrics": {...}}}
    manifest: dict,
) -> str:
    lines = []
    lines.append(f"# Ruleset comparison — {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Corpus: {len(manifest['memory_to_scenarios'])} memories. Scenarios: `{scenario_set['description']}`")
    lines.append("")

    lines.append("## Rulesets compared")
    lines.append("")
    for r in ruleset_names:
        cfg = load_ruleset(r)
        lines.append(f"- **{r}** — {cfg['description']}")
    lines.append("")

    lines.append("## Summary by scenario")
    lines.append("")
    header_cols = ["Scenario", "Phase", "Expected"] + [f"{r}: hits / P@5 / rank₁" for r in ruleset_names]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")

    for scen in scenario_set["scenarios"]:
        row = [scen["id"], str(scen["phase"])]
        # how many expected are actually in the corpus (vs requested tags that have no hits)
        expected_mids = set()
        for tag in scen["expected_hit_tags"]:
            for mid in manifest["scenario_to_memories"].get(tag, []):
                expected_mids.add(mid)
        row.append(str(len(expected_mids)))
        for r in ruleset_names:
            m = results[(r, scen["id"])]["metrics"]
            hits = f"{m['hits_total']}/{m['expected_in_corpus']}"
            p5 = f"{m['precision_at_k']:.2f}"
            rk = m["rank_of_first_hit"] if m["rank_of_first_hit"] else "—"
            row.append(f"{hits} · {p5} · {rk}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("**Legend:** `hits / expected · P@5 · rank of first hit`. Rank `—` = no expected hit appeared in the returned set.")
    lines.append("")

    # Winner analysis
    lines.append("## Head-to-head")
    lines.append("")
    if len(ruleset_names) == 2:
        a, b = ruleset_names
        wins = {a: 0, b: 0, "tie": 0}
        for scen in scenario_set["scenarios"]:
            m_a = results[(a, scen["id"])]["metrics"]
            m_b = results[(b, scen["id"])]["metrics"]
            # Primary metric: hits_total. Tie-break: rank_of_first_hit (lower is better).
            if m_a["hits_total"] > m_b["hits_total"]:
                wins[a] += 1
            elif m_b["hits_total"] > m_a["hits_total"]:
                wins[b] += 1
            else:
                r_a = m_a["rank_of_first_hit"] or 999
                r_b = m_b["rank_of_first_hit"] or 999
                if r_a < r_b:
                    wins[a] += 1
                elif r_b < r_a:
                    wins[b] += 1
                else:
                    wins["tie"] += 1
        lines.append(f"- **{a}** wins: {wins[a]}")
        lines.append(f"- **{b}** wins: {wins[b]}")
        lines.append(f"- Ties: {wins['tie']}")
    lines.append("")

    # Per-scenario detail appendix
    lines.append("## Per-scenario detail")
    lines.append("")
    for scen in scenario_set["scenarios"]:
        lines.append(f"### {scen['id']} (phase {scen['phase']})")
        lines.append(f"_{scen['description']}_")
        lines.append("")
        if scen.get("query"):
            lines.append(f"Query: `{scen['query']}`")
        if scen.get("project_slug"):
            lines.append(f"Project: `{scen['project_slug']}`")
        lines.append("")
        for r in ruleset_names:
            entry = results[(r, scen["id"])]
            m = entry["metrics"]
            lines.append(f"**{r}** — params: `{json.dumps(entry['run']['params'], separators=(',', ':'))}`")
            lines.append("")
            lines.append(f"  - returned: {m['results_returned']}, hits: {m['hits_total']}/{m['expected_in_corpus']}, P@5: {m['precision_at_k']:.2f}, first hit at rank: {m['rank_of_first_hit']}, top score: {m['top_score']}")
            # Show top 3 surfaced contents
            top = entry["run"]["response"].get("results", [])[:3]
            for i, item in enumerate(top, 1):
                mid = item.get("id") or item.get("memory", {}).get("id")
                content = (item.get("memory", {}).get("content") or "")[:90]
                score = item.get("final_score") or item.get("score") or 0
                is_hit = "✓" if mid in {mm for s in scen["expected_hit_tags"] for mm in manifest["scenario_to_memories"].get(s, [])} else " "
                lines.append(f"    {i}. {is_hit} [{score:.3f}] {content}…")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    ap.add_argument("--rulesets", nargs="+", default=["baseline_v1", "bare_tag_1m_v2"])
    ap.add_argument("--scenarios", default="session_start_v1")
    ap.add_argument("--manifest", default="corpus_v1.manifest.json")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    scen_set = load_scenarios(args.scenarios)
    rulesets = {name: load_ruleset(name) for name in args.rulesets}

    print(f"running {len(scen_set['scenarios'])} scenarios under {len(rulesets)} rulesets")

    all_results: dict = {}
    for ruleset_name, ruleset in rulesets.items():
        print(f"  ruleset: {ruleset_name}")
        for scen in scen_set["scenarios"]:
            try:
                run = run_phase(args.endpoint, args.token, ruleset, scen["phase"], scen)
                metrics = score_scenario(run, scen, manifest)
                all_results[(ruleset_name, scen["id"])] = {"run": run, "metrics": metrics}
                print(f"    {scen['id']}: hits={metrics['hits_total']}/{metrics['expected_in_corpus']} P@5={metrics['precision_at_k']:.2f} rank1={metrics['rank_of_first_hit']}")
            except Exception as e:
                print(f"    {scen['id']}: ERROR — {e}")
                all_results[(ruleset_name, scen["id"])] = {"run": {"params": {}, "response": {"results": []}}, "metrics": {"results_returned": 0, "expected_in_corpus": 0, "hits_total": 0, "hits_in_top_k": 0, "precision_at_k": 0.0, "recall": 0.0, "rank_of_first_hit": None, "top_score": None}}

    report = format_report(args.rulesets, scen_set, all_results, manifest)
    out_path = HERE / "data" / "results" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-comparison.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"\nreport: {out_path.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
