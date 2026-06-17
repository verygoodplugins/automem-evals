"""End-to-end smoke: 2 stacks on a tiny synthetic corpus, no production clone.

Run:
  AUTOMEM_DIR=/path/to/automem \
  python -m runners.matrix.smoke
"""

import sys
from pathlib import Path

import os

from . import live as live_mod
from . import orchestrator
from . import score as score_mod

_here = Path(__file__).resolve()
_candidates = [_here.parents[3] / "automem", Path.home() / "Projects" / "OpenAI" / "automem"]
_default = next((str(c) for c in _candidates if (c / "automem").is_dir()), str(_candidates[0]))
_AUTOMEM = os.environ.get("AUTOMEM_DIR", _default)
sys.path.insert(0, str(Path(_AUTOMEM) / "scripts" / "lab"))
import lab_corpus  # noqa: E402

SYNTH_MEMORIES = [
    {
        "content": f"Synthetic memory {i}: project alpha decision about topic {i}.",
        "tags": ["smoke"],
        "importance": 0.6,
    }
    for i in range(10)
]


def _seed(api_url, headers):
    ids = []
    for m in SYNTH_MEMORIES:
        r = lab_corpus.requests.post(
            f"{api_url}/memory", json=m, headers=headers, timeout=30
        )
        r.raise_for_status()
        d = r.json()
        ids.append(
            str(d.get("memory_id") or d.get("id") or (d.get("memory") or {}).get("id"))
        )
    return ids


def main() -> int:
    headers = live_mod._headers()
    provider = live_mod.LiveProvider(automem_dir=_AUTOMEM, base_api=18001)
    results_dir = "data/results/matrix-smoke"

    # Build queries + distractors lazily per stack inside score.
    def provision(name, config):
        url = provider.provision(name, config)
        seeded = _seed(url, headers)
        distractors = set(
            lab_corpus.inject_distractors(
                url, headers, lab_corpus.make_distractor_memories(5)
            )
        )
        provider._smoke = {
            "queries": [
                {
                    "query": SYNTH_MEMORIES[i]["content"][:40],
                    "expected_ids": [seeded[i]],
                    "category": "smoke",
                }
                for i in range(len(seeded))
            ],
            "distractors": distractors,
        }
        return url

    def score(api_url, name, config):
        s = provider._smoke
        return score_mod.score_stack(
            api_url,
            headers,
            s["queries"],
            distractor_ids=s["distractors"],
            config=config,
        )

    out = orchestrator.run_matrix(
        [
            {
                "name": "baseline",
                "config": {
                    "SEARCH_WEIGHT_VECTOR": "0.35",
                    "SEARCH_WEIGHT_KEYWORD": "0.35",
                },
            },
            {
                "name": "simpler",
                "config": {
                    "SEARCH_WEIGHT_VECTOR": "0.35",
                    "SEARCH_WEIGHT_KEYWORD": "0.0",
                },
            },
        ],
        results_dir=results_dir,
        automem_commit="smoke",
        snapshot_id="synthetic",
        seed=42,
        baseline_name="baseline",
        provision=provision,
        score=score,
        teardown=provider.teardown,
    )
    print("WINNER:", out["winner"])
    print(
        "ROWS:", [(r.name, r.status, r.scorecard.get("ndcg_10")) for r in out["rows"]]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
