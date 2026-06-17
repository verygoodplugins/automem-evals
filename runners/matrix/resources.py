"""Deterministic host-port allocation and RAM-based concurrency for the matrix."""

import math
from typing import Dict


def cell_ports(index: int, base_api: int = 18001) -> Dict[str, int]:
    base = base_api + index * 10
    return {"api": base, "falkor": base + 1, "falkor_ui": base + 2, "qdrant": base + 3}


def max_concurrency(total_gb: float, per_stack_gb: float, headroom: float = 0.8) -> int:
    if per_stack_gb <= 0:
        return 1
    return max(1, math.floor(total_gb * headroom / per_stack_gb))
