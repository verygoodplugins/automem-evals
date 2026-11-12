"""MEMPROBE / MemAudit (arXiv:2606.24595) adapter scaffold for AutoMem.

Scaffold only. It vendors no upstream code or data, calls no model, and
produces no AutoMem score: every report it can emit is ``not_scored``.
Upstream (CC BY 4.0) is fetched by commit into an untracked checkout and
verified before use. Protocol mapping and acceptance criteria: issue #100.

Access modes mirror the paper: ``full_store`` enumerates one user's isolated
tag through GET /memory/by-tag; ``top_k`` is GET /recall with the same tag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

ARXIV_ID = "2606.24595"
UPSTREAM_REPO = "https://github.com/sora1998/MEMAUDIT-bench"
UPSTREAM_COMMIT = "0c20cf72f489a00e7614bd5eefb0aa94098ec93b"  # main, 2026-09-25
UPSTREAM_PAPER_V1_COMMIT = "42a8323a34cabff4b6477f0ce060f54ca94112f3"
UPSTREAM_LICENSE = "CC-BY-4.0"
BANK_PATH = "Deeppersona/data/user_memory_banks_pooled_final.json"
BANK_SHA256 = "7731d47767ec1f9e8d725e750540dfa8d8557fb9687fff3666436ef3573bf3e4"
CATEGORY_COUNTS = {
    "skill_memory": 7,
    "knowledge_memory": 7,
    "episodic_memory": 7,
    "self_model": 5,
    "assistance_preference": 5,
}
N_USERS = 50
TOP_K = 5
ACCESS_MODES = ("full_store", "top_k")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
JUDGE_SCALE = {0.0, 0.25, 0.5, 0.75, 1.0}
_SAFE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class ProtocolError(RuntimeError):
    """AutoMem returned something the adapter will not paper over."""


def assert_loopback(endpoint: str) -> str:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit(f"invalid endpoint: {endpoint}")
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise SystemExit(f"refusing non-loopback endpoint: {endpoint}")
    return endpoint.rstrip("/")


def http_transport(endpoint: str, token: str, timeout: float = 60.0) -> Transport:
    base = assert_loopback(endpoint)

    def get(path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(f"{base}{path}?{query}", headers={"X-Api-Key": token})
        with urllib.request.urlopen(req, timeout=timeout) as response:  # errors propagate
            return json.loads(response.read().decode("utf-8"))

    return get


def user_tag(run_id: str, user_id: str) -> str:
    """Isolated per-user tag. Lowercase only: AutoMem lowercases stored tags."""
    for label, value in (("run_id", run_id), ("user_id", user_id)):
        if not _SAFE.match(value):
            raise ValueError(f"{label} must match {_SAFE.pattern}: {value!r}")
    return f"memprobe:{run_id}:{user_id}"


def verify_checkout(checkout: Path, run: Callable[..., Any] = subprocess.run) -> None:
    try:
        out = run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise SystemExit(f"cannot read git HEAD of {checkout}: {exc}") from exc
    head = out.stdout.strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"upstream checkout is {head}, expected pinned {UPSTREAM_COMMIT}")


@dataclass(frozen=True)
class Target:
    user_id: str
    category: str
    dimension: str
    ground_truth: str = field(repr=False)
    explanation: str = field(repr=False)

    def probe(self) -> dict[str, str]:
        """Everything the reader may see. Never the reference value or explanation."""
        return {"user_id": self.user_id, "category": self.category, "dimension": self.dimension}


def load_bank(
    path: Path, *, expected_sha256: str = BANK_SHA256, expected_users: int = N_USERS
) -> list[Target]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(f"bank sha256 {digest} != pinned {expected_sha256}")
    users = json.loads(raw).get("users") or []
    if len(users) != expected_users:
        raise ValueError(f"expected {expected_users} users, found {len(users)}")
    targets: list[Target] = []
    for user in users:
        bank = user["memory_bank"]
        for category, count in CATEGORY_COUNTS.items():
            entries = bank.get(category) or []
            if len(entries) != count:
                raise ValueError(f"{user['user_id']} {category}: {len(entries)} entries, expected {count}")
            targets.extend(
                Target(user["user_id"], category, e["dimension"], e["short"], e["explanation"])
                for e in entries
            )
    return targets


def probe_query(category: str, dimension: str, guide: str = "") -> str:
    """Probe text. Takes no reference value or explanation, by construction.

    ``guide`` is the generic category definition read from the pinned upstream
    ``scorer.py`` at run time; it is not copied into this repo.
    """
    return f"What best describes the user's {dimension.replace('_', ' ')}? {guide}".strip()


def _tags(memory: dict[str, Any]) -> list[str]:
    return [str(t).lower() for t in memory.get("tags") or []]


def _normalize_recall(result: dict[str, Any]) -> dict[str, Any]:
    memory = result["memory"] if isinstance(result.get("memory"), dict) else result
    keys = ("id", "content", "tags", "t_valid", "t_invalid")
    return {**{k: memory.get(k) for k in keys}, "score": result.get("score", result.get("final_score"))}


class AutoMemReader:
    """Reads one user's isolated store through the two paper access modes."""

    def __init__(self, transport: Transport, *, page_size: int = 200, max_items: int = 5000):
        self.get, self.page_size, self.max_items = transport, page_size, max_items

    def full_store(self, tag: str) -> list[dict[str, Any]]:
        """Enumerate every memory carrying ``tag``, paging by-tag to exhaustion."""
        out: list[dict[str, Any]] = []
        offset = 0
        while True:
            env = self.get("/memory/by-tag", {"tags": tag, "limit": self.page_size, "offset": offset})
            page = env.get("memories")
            if not isinstance(page, list):
                raise ProtocolError(f"/memory/by-tag returned no memories list: {sorted(env)}")
            out.extend(m for m in page if tag in _tags(m))  # drop prefix over-matches
            offset += len(page)
            if not env.get("has_more"):
                return out
            if not page or offset >= self.max_items:
                raise ProtocolError(f"/memory/by-tag pagination did not terminate at offset {offset}")

    def top_k(self, tag: str, query: str, k: int = TOP_K) -> list[dict[str, Any]]:
        env = self.get(
            "/recall",
            {"query": query, "tags": [tag], "tag_mode": "all", "tag_match": "exact", "limit": k},
        )
        results = env.get("results")
        if not isinstance(results, list):
            raise ProtocolError(f"/recall returned no results list: {sorted(env)}")
        return [_normalize_recall(r) for r in results][:k]


def footprint(memories: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Store size plus how many records carry t_invalid (superseded but still enumerable)."""
    items = list(memories)
    chars = sum(len(str(m.get("content") or "")) for m in items)
    return {
        "items": len(items),
        "mean_chars": chars / len(items) if items else 0.0,
        "invalidated": sum(1 for m in items if m.get("t_invalid")),
    }


def _is_abstention(predicted: Any) -> bool:
    return predicted is None or str(predicted).strip().lower() in {"", "unknown"}


def _macro(details: list[dict[str, Any]]) -> float | None:
    """Category-balanced mean: average within category, then across categories."""
    by_cat: dict[str, list[float]] = {}
    for d in details:
        by_cat.setdefault(d["category"], []).append(float(d["score"]))
    means = [sum(v) / len(v) for v in by_cat.values()]
    return sum(means) / len(means) if means else None


def summarize(details: list[dict[str, Any]], *, judge_available: bool) -> dict[str, Any]:
    """Recovery, answer and abstention metrics, kept separate.

    ``details``: one dict per target with ``category``, ``predicted`` and
    ``score`` (judge output, None when no judge ran). Any missing score, or no
    judge at all, yields ``not_scored`` with every metric null.
    """
    n = len(details)
    n_scored = sum(1 for d in details if d.get("score") is not None)
    base = {"n_targets": n, "n_scored": n_scored}
    nulls = {"recovery": None, "answer_rate": None, "abstention_rate": None, "answered_recovery": None}
    if not judge_available or n == 0 or n_scored != n:
        reason = "judge unavailable" if not judge_available else "targets missing judge scores"
        return {"status": "not_scored", "reason": reason, **base, **nulls}
    bad = [d["score"] for d in details if float(d["score"]) not in JUDGE_SCALE]
    if bad:
        raise ValueError(f"scores outside the 5-level judge scale: {bad[:3]}")
    answered = [d for d in details if not _is_abstention(d.get("predicted"))]
    return {
        "status": "scored",
        "reason": None,
        **base,
        "recovery": _macro(details),
        "answer_rate": len(answered) / n,
        "abstention_rate": (n - len(answered)) / n,
        "answered_recovery": _macro(answered),
    }


def build_report(*, access_mode: str, run_id: str, endpoint: str, summary: dict[str, Any]) -> dict:
    if access_mode not in ACCESS_MODES:
        raise ValueError(f"access_mode must be one of {ACCESS_MODES}")
    return {
        "benchmark": "memprobe",
        "arxiv_id": ARXIV_ID,
        "upstream": {"repo": UPSTREAM_REPO, "commit": UPSTREAM_COMMIT, "license": UPSTREAM_LICENSE},
        "access_mode": access_mode,
        "k": TOP_K if access_mode == "top_k" else None,
        "run_id": run_id,
        "endpoint": assert_loopback(endpoint),
        "paper_comparable": False,
        **summary,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify the pinned upstream and emit a not_scored plan.")
    ap.add_argument("--checkout", type=Path, required=True, help="untracked clone at the pinned commit")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--endpoint", default="http://localhost:8001")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    verify_checkout(args.checkout)
    targets = load_bank(args.checkout / BANK_PATH)
    users = sorted({t.user_id for t in targets})
    plan = {
        "n_users": len(users),
        "n_targets": len(targets),
        "tags": {u: user_tag(args.run_id, u) for u in users},
        "reports": [
            build_report(
                access_mode=mode,
                run_id=args.run_id,
                endpoint=args.endpoint,
                summary=summarize([], judge_available=False),
            )
            for mode in ACCESS_MODES
        ],
    }
    text = json.dumps(plan, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
