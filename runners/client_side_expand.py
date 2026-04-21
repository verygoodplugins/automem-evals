#!/usr/bin/env python3
"""
Prototype: client-side graph expansion.

Server-side `expand_relations: true` is a no-op under tag-gated recall (the tag
filter is applied to expansion targets, so cross-boundary memories never
surface). However, the server DOES return each result's outgoing `.relations[]`
inline — the graph is visible to the caller; it's just not promoted into
results.

This script runs a tag-gated recall, then walks the inline relations to collect
memories that would have been in an unfiltered expansion pass. Those get merged
into the results with a synthetic score boost. Then scores against expected
hits the same way compare_rulesets does.

Usage:
  python3 runners/client_side_expand.py \
      --ruleset bare_tag_1m_v2 \
      --scenarios graph_expansion_v1
"""

import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = HERE / "data" / "seed_memories" / "corpus_v1.manifest.json"
ENDPOINT = "http://localhost:8001"
TOKEN = "test-token"


def http(method: str, url: str, params: dict | None = None) -> dict:
    headers = {"X-Api-Key": TOKEN}
    if method == "GET" and params:
        flat = []
        for k, v in params.items():
            if isinstance(v, list):
                flat.extend((k, str(x)) for x in v)
            elif isinstance(v, bool):
                flat.append((k, "true" if v else "false"))
            elif v is not None:
                flat.append((k, str(v)))
        url = f"{url}?{urllib.parse.urlencode(flat)}"
    req = urllib.request.Request(url, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def run_phase2(ruleset: dict, scenario: dict) -> dict:
    cfg = ruleset["phase_2_task_context"]
    params = {}
    q = scenario["query"]
    suffixes = cfg.get("queries_suffix", [])
    proj = scenario.get("project_slug") or ""
    suffixes = [s.replace("<project>", proj) for s in suffixes if "<project>" not in s or proj]
    params["queries"] = [q] + suffixes if q else suffixes
    if cfg.get("tags_from") == "project_slug" and scenario.get("project_slug"):
        params["tags"] = [scenario["project_slug"]]
        params["tag_match"] = "exact"
    if cfg.get("auto_decompose"):
        params["auto_decompose"] = True
    if cfg.get("time_query"):
        params["time_query"] = cfg["time_query"]
    params["limit"] = cfg["limit"]
    return http("GET", f"{ENDPOINT}/recall", params)


def client_expand(
    response: dict,
    min_strength: float = 0.6,
    max_per_seed: int = 3,
    allowed_types: set[str] = None,
) -> list[dict]:
    """Collect related memories from .results[].relations[] and attach as synthetic results."""
    allowed_types = allowed_types or {
        # Authorable edges worth promoting
        "LEADS_TO", "EVOLVED_INTO", "EXEMPLIFIES", "DERIVED_FROM",
        "REINFORCES", "PREFERS_OVER", "PART_OF", "RELATES_TO",
        # Skip noisy system-generated edges
        # not in set: SIMILAR_TO, PRECEDED_BY, EXPLAINS, SHARES_THEME, PARALLEL_CONTEXT, DISCOVERED
    }
    seen_ids = {r.get("id") for r in response.get("results", [])}
    expanded = []
    for seed in response.get("results", []):
        rels = seed.get("relations", [])
        # Sort relations by strength desc
        rels = sorted(rels, key=lambda r: r.get("strength", 0), reverse=True)
        kept = 0
        for rel in rels:
            if kept >= max_per_seed:
                break
            if rel.get("type") not in allowed_types:
                continue
            if rel.get("strength", 0) < min_strength:
                continue
            rel_mem = rel.get("memory", {})
            mid = rel_mem.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            # Synthetic: copy seed score, downrank by 0.1 per hop
            synth_score = (seed.get("final_score") or 0) * 0.9
            expanded.append({
                "id": mid,
                "memory": rel_mem,
                "final_score": synth_score,
                "match_type": "client_expand",
                "via": {"seed_id": seed.get("id"), "type": rel.get("type"), "strength": rel.get("strength")},
            })
            kept += 1
    return expanded


def score(results: list[dict], expected_mids: set[str], k: int = 5) -> dict:
    ranked = [r.get("id") for r in results]
    topk = ranked[:k]
    hits_topk = sum(1 for m in topk if m in expected_mids)
    hits_total = sum(1 for m in ranked if m in expected_mids)
    first_rank = next((i + 1 for i, m in enumerate(ranked) if m in expected_mids), None)
    return {
        "returned": len(ranked),
        "hits_total": hits_total,
        "expected_in_corpus": len(expected_mids),
        "p_at_k": hits_topk / max(len(topk), 1),
        "first_rank": first_rank,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruleset", default="bare_tag_1m_v2")
    ap.add_argument("--scenarios", default="graph_expansion_v1")
    args = ap.parse_args()

    ruleset = json.loads((HERE / "rulesets" / f"{args.ruleset}.json").read_text())
    scenarios = json.loads((HERE / "scenarios" / f"{args.scenarios}.json").read_text())
    manifest = json.loads(MANIFEST.read_text())

    print(f"ruleset={args.ruleset}  scenarios={args.scenarios}")
    print(f"{'scenario':<28} {'server_hits':<14} {'+client_exp_hits':<18} {'expanded_added':<16}")

    for scen in scenarios["scenarios"]:
        expected_mids = set()
        for tag in scen["expected_hit_tags"]:
            for mid in manifest["scenario_to_memories"].get(tag, []):
                expected_mids.add(mid)

        resp = run_phase2(ruleset, scen)
        server_results = resp.get("results", [])
        server_score = score(server_results, expected_mids)

        expanded = client_expand(resp)
        combined = server_results + expanded
        combined_score = score(combined, expected_mids)

        added_hits = combined_score["hits_total"] - server_score["hits_total"]
        print(
            f"{scen['id']:<28} "
            f"{server_score['hits_total']}/{server_score['expected_in_corpus']:<12} "
            f"{combined_score['hits_total']}/{combined_score['expected_in_corpus']:<16} "
            f"+{added_hits} (of {len(expanded)} expanded)"
        )

        # Detail: show what was expanded
        for e in expanded:
            is_hit = "✓" if e["id"] in expected_mids else " "
            via = e.get("via", {})
            snippet = (e.get("memory", {}).get("content") or e.get("memory", {}).get("summary") or "")[:70]
            print(f"    {is_hit} [{e['final_score']:.3f}] via {via.get('type')} s={via.get('strength')}: {snippet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
