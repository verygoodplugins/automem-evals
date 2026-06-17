"""Provenance manifest + cell keying for the parallel matrix harness.

A cell is uniquely identified by (config, automem_commit, seed, snapshot_id).
Its result JSON is the durable record; existence == done (idempotent resume).
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


def cell_key(
    config: Dict[str, Any], automem_commit: str, seed: int, snapshot_id: str
) -> str:
    payload = json.dumps(
        {
            "config": config,
            "commit": automem_commit,
            "seed": seed,
            "snapshot": snapshot_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class ManifestRow:
    name: str
    key: str
    config: Dict[str, Any]
    automem_commit: str
    seed: int
    snapshot_id: str
    scorecard: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "key": self.key,
            "config": self.config,
            "automem_commit": self.automem_commit,
            "seed": self.seed,
            "snapshot_id": self.snapshot_id,
            "scorecard": self.scorecard,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ManifestRow":
        return cls(
            name=d["name"],
            key=d["key"],
            config=d.get("config", {}),
            automem_commit=d.get("automem_commit", ""),
            seed=d.get("seed", 0),
            snapshot_id=d.get("snapshot_id", ""),
            scorecard=d.get("scorecard", {}),
            status=d.get("status", "ok"),
        )


def result_path(results_dir: str, key: str) -> Path:
    return Path(results_dir) / f"{key}.json"


def is_cached(results_dir: str, key: str) -> bool:
    return result_path(results_dir, key).exists()


def save_row(results_dir: str, row: ManifestRow) -> Path:
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    final = result_path(results_dir, row.key)
    tmp = final.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(row.to_dict(), indent=2))
    os.replace(tmp, final)
    return final


def load_rows(results_dir: str) -> List[ManifestRow]:
    p = Path(results_dir)
    if not p.exists():
        return []
    return [
        ManifestRow.from_dict(json.loads(f.read_text()))
        for f in sorted(p.glob("*.json"))
    ]
