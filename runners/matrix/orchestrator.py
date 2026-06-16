"""Sequential matrix orchestrator: provision -> score -> teardown per config,
idempotent resume via the manifest, winner via lab_metrics.pick_winner.

Concurrency is intentionally left to the caller/runner; this core is sequential
and deterministic so it is fully unit-testable with injected provider/scorer.
"""

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

import os

from . import manifest as mf

_AUTOMEM = os.environ.get("AUTOMEM_DIR", "/Users/jgarturo/Projects/OpenAI/automem")
sys.path.insert(0, str(Path(_AUTOMEM) / "scripts" / "lab"))
import lab_metrics  # noqa: E402


def run_matrix(
    configs: List[Dict[str, Any]],
    *,
    results_dir: str,
    automem_commit: str,
    snapshot_id: str,
    seed: int,
    baseline_name: str,
    provision: Callable[[str, Dict[str, Any]], str],
    score: Callable[[str, str, Dict[str, Any]], Dict[str, Any]],
    teardown: Callable[[str], None],
) -> Dict[str, Any]:
    for entry in configs:
        name, config = entry["name"], entry["config"]
        key = mf.cell_key({"_name": name, **config}, automem_commit, seed, snapshot_id)
        if mf.is_cached(results_dir, key):
            continue
        status, scorecard = "ok", {}
        try:
            api_url = provision(name, config)
            scorecard = score(api_url, name, config)
        except Exception as e:  # noqa: BLE001
            status = "error"
            scorecard = {"error": str(e)}
        finally:
            try:
                teardown(name)
            except Exception:  # noqa: BLE001
                pass
        mf.save_row(
            results_dir,
            mf.ManifestRow(
                name=name,
                key=key,
                config=config,
                automem_commit=automem_commit,
                seed=seed,
                snapshot_id=snapshot_id,
                scorecard={**scorecard, "name": name},
                status=status,
            ),
        )

    rows = mf.load_rows(results_dir)
    cards = [r.scorecard for r in rows if r.status == "ok" and "ndcg_10" in r.scorecard]
    winner = (
        lab_metrics.pick_winner(cards, baseline_name=baseline_name) if cards else None
    )
    return {"winner": winner, "rows": rows}
