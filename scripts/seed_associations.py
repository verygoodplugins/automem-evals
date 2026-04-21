#!/usr/bin/env python3
"""
Create a curated association graph over the seeded corpus.

The evals corpus has rich content but no explicit edges (store_memory doesn't
create associations automatically). This script resolves the scenario-hit
manifest to memory_ids and creates typed edges that mirror how a disciplined
user would use associate_memories:

  - LEADS_TO — problem → solution, decision → downstream milestone
  - EVOLVED_INTO — old state → new state
  - EXEMPLIFIES — concrete instance → abstract pattern
  - REINFORCES — supporting evidence across project boundaries

The goal is to let the `expand_relations` experiment measure whether graph
traversal surfaces relevant-but-untagged memories.

Usage:
  python3 scripts/seed_associations.py [--endpoint http://localhost:8001] [--token test-token]
"""

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = HERE / "data" / "seed_memories" / "corpus_v1.manifest.json"


def request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Api-Key": token},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# Edges to create, expressed in scenario-id terms. Each entry: (from_scenario,
# to_scenario, relation_type, strength, rationale).
#
# Some scenarios map to multiple memory_ids; we create a single edge between
# the FIRST memory of each side, not the full bipartite product, to avoid
# pathological expansion during recall.
#
# Chosen to exercise cross-type and cross-project paths.
EDGES = [
    # Within tensor-pipeline: OAuth decision led to the token-rotation bug fix
    ("TP-AUTH", "DEBUG-AUTH", "LEADS_TO", 0.9,
     "OAuth2+PKCE decision exposed the token-rotation gap on user-initiated logout."),
    # Retry budget decision led to P99 improvement
    ("TP-RETRY", "TP-RETRY", "LEADS_TO", 0.85,
     "Retry budget shipped → P99 latency dropped 15%."),
    # CI bug fix → CI isolation milestone
    ("DEBUG-CI", "TP-CI", "LEADS_TO", 0.9,
     "Test port-race fix → flake rate dropped 8%→0.3%."),
    # Fastify architecture decision → Fastify migration complete milestone
    ("TP-ARCH", "TP-ARCH", "EVOLVED_INTO", 0.85,
     "Express→Fastify decision evolved into migration-complete state."),
    # Dashboard-app hydration bug → discriminated-union pattern
    ("DEBUG-HYDRATE", "DA-PATTERN", "LEADS_TO", 0.7,
     "Hydration mismatch pain → adopt discriminated unions for async states."),
    # Dashboard-app RSC decision → v4 milestone
    ("DA-RSC", "DA-RSC", "LEADS_TO", 0.85,
     "RSC adoption decision led to v4.0 shipping."),
    # Preference about bare tags REINFORCES the AutoMem markdown-memory preference
    ("PREF-MEMORY", "PREF-MEMORY", "REINFORCES", 0.8,
     "Both PREF-MEMORY entries reinforce each other's constraint on memory tooling."),
    # Old-service sunset announcement → read-only mode milestone
    ("OS-SUNSET", "OS-SUNSET", "EVOLVED_INTO", 0.85,
     "Sunset announcement evolved into read-only mode deployment."),
    # Cross-project: tensor-pipeline retry pattern EXEMPLIFIES cross-project observability pattern
    # (connect a TP memory to a generic observability memory if they exist)
    # — skipped because our generic pattern isn't in the scenario_to_memories map.
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--token", default="test-token")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    scen_to_mids: dict[str, list[str]] = manifest["scenario_to_memories"]

    created = 0
    skipped = 0
    failures = 0

    for from_scen, to_scen, rtype, strength, reason in EDGES:
        from_mids = scen_to_mids.get(from_scen, [])
        to_mids = scen_to_mids.get(to_scen, [])

        if not from_mids or not to_mids:
            print(f"  SKIP {from_scen} -[{rtype}]-> {to_scen}: missing memory ids")
            skipped += 1
            continue

        # When the same scenario has multiple memories and we're linking within
        # it (e.g., decision → milestone where both are tagged TP-RETRY), pick
        # the oldest → newest to express "earlier led to later."
        from_mid = from_mids[0]
        to_mid = to_mids[-1] if from_scen == to_scen and len(to_mids) > 1 else to_mids[0]

        if from_mid == to_mid:
            # Can't self-associate; pick the next.
            if len(to_mids) > 1:
                to_mid = to_mids[1]
            else:
                print(f"  SKIP {from_scen} -[{rtype}]-> {to_scen}: only one memory in both sides")
                skipped += 1
                continue

        try:
            request("POST", f"{args.endpoint}/associate", args.token, {
                "memory1_id": from_mid,
                "memory2_id": to_mid,
                "type": rtype,
                "strength": strength,
            })
            print(f"  [{rtype}] {from_scen}→{to_scen} ({strength}): {reason}")
            created += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            print(f"  FAIL {from_scen}→{to_scen}: HTTP {e.code} {body}")
            failures += 1

    print(f"\ncreated={created} skipped={skipped} failures={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
