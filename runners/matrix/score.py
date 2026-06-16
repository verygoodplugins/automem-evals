"""Score one configured stack with the Plan A scorecard primitives.

Imports lab_corpus / lab_metrics from the automem repo (single source of truth).
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import os

_AUTOMEM = os.environ.get("AUTOMEM_DIR", "/Users/jgarturo/Projects/OpenAI/automem")
sys.path.insert(0, str(Path(_AUTOMEM) / "scripts" / "lab"))

import lab_corpus  # noqa: E402
import lab_metrics  # noqa: E402


def score_stack(
    api_url: str,
    headers: Dict[str, str],
    queries: List[Dict[str, Any]],
    *,
    distractor_ids: Optional[Iterable[str]] = None,
    recall_params: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    recall_fn=lab_corpus.recall,
) -> Dict[str, Any]:
    distractor_ids = set(distractor_ids or set())
    recall_params = recall_params or {}
    ndcgs: List[float] = []
    drates: List[float] = []
    latencies: List[float] = []

    for q in queries:
        start = time.perf_counter()
        data = recall_fn(api_url, headers, q["query"], **recall_params)
        latencies.append((time.perf_counter() - start) * 1000)
        retrieved = lab_corpus.extract_ids(data)
        ndcgs.append(lab_metrics.ndcg_at_k(retrieved, q.get("expected_ids", []), 10))
        drates.append(lab_metrics.distractor_rate_at_k(retrieved, distractor_ids, 10))

    n = max(len(queries), 1)
    return {
        "ndcg_10": sum(ndcgs) / n,
        "distractor_rate_10": sum(drates) / n,
        "latency_ms": sum(latencies) / n,
        "complexity": lab_metrics.config_complexity(config or {}),
    }
