"""MERIT ``MemoryBase``-compatible AutoMem adapter.

This module intentionally does not vendor MERIT.  It is used with the official
``smshweta/merit-bench`` checkout pinned by :mod:`run_merit`.  It implements two
write policies over the same isolated local AutoMem namespace:

* ``plain`` retains every extracted fact record; and
* ``supersede-on-write`` stores an explicit replacement with
  ``supersedes_memory_id`` when the same MERIT fact key changes.

The fact-key patterns mirror the public MIT-licensed MERIT ``StructuredFacts``
condition at revision 293933d96b1d1849e1f20d1bb324def5de9ed33f.  They are kept
small and explicit so update semantics are measurable rather than inferred from
a model response.
"""
from __future__ import annotations

import json
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


Variant = Literal["plain", "supersede-on-write"]
HttpRequest = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def is_local_endpoint(endpoint: str) -> bool:
    """Return whether an endpoint is an explicit loopback AutoMem endpoint."""
    host = (urlparse(endpoint).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


@dataclass
class MeteringSnapshot:
    """Memory-operation metering, separating measured from estimated values.

    AutoMem's HTTP API does not promise model-side usage in every response.
    Therefore request/response character estimates are disclosed separately and
    dollars remain ``None`` until the caller supplies a price or the server
    returns a measured ``cost_usd`` field.  This prevents an unknown cost from
    silently becoming a $0 result.
    """

    calls: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    measured_input_tokens: int | None = None
    measured_output_tokens: int | None = None
    measured_embedding_tokens: int | None = None
    measured_cost_usd: float | None = None

    def record(self, request_body: dict[str, Any] | None, response: dict[str, Any]) -> None:
        self.calls += 1
        request_text = json.dumps(request_body or {}, sort_keys=True)
        response_text = json.dumps(response, sort_keys=True)
        self.estimated_input_tokens += math.ceil(len(request_text) / 4)
        self.estimated_output_tokens += math.ceil(len(response_text) / 4)

        usage = response.get("usage") or response.get("metering") or {}
        if not isinstance(usage, dict):
            return
        self.measured_input_tokens = _add_optional(
            self.measured_input_tokens, usage.get("prompt_tokens", usage.get("input_tokens"))
        )
        self.measured_output_tokens = _add_optional(
            self.measured_output_tokens, usage.get("completion_tokens", usage.get("output_tokens"))
        )
        self.measured_embedding_tokens = _add_optional(
            self.measured_embedding_tokens, usage.get("embedding_tokens")
        )
        cost = usage.get("cost_usd", response.get("cost_usd"))
        if isinstance(cost, (int, float)):
            self.measured_cost_usd = (self.measured_cost_usd or 0.0) + float(cost)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "measured_input_tokens": self.measured_input_tokens,
            "measured_output_tokens": self.measured_output_tokens,
            "measured_embedding_tokens": self.measured_embedding_tokens,
            "measured_cost_usd": self.measured_cost_usd,
        }


def _add_optional(previous: int | None, value: Any) -> int | None:
    return (previous or 0) + int(value) if isinstance(value, (int, float)) else previous


@dataclass(frozen=True)
class Fact:
    key: str
    value: str


_FACT_PATTERNS: tuple[tuple[re.Pattern[str], str, int | str, int], ...] = (
    # D1 customer support
    (re.compile(r'"customer_id":\s*"([^"]+)".*?"address":\s*"([^"]+)"'), "address", 1, 2),
    (re.compile(r'"order_id":\s*"([^"]+)".*?"refunded_cents":\s*(\d+)'), "refunded_cents", 1, 2),
    (re.compile(r'agreed amount of (\d+) cents for order (ORD-\d+)'), "agreed_refund_cents", 2, 1),
    # D2 IT operations
    (re.compile(r'planned fix: (\w+=\d+) for ([a-z-]+-api)'), "planned_fix", 2, 1),
    (re.compile(r'rollback target (v[\d.]+) for ([a-z-]+-api)'), "rollback_target", 2, 1),
    (re.compile(r'"service":\s*"([^"]+)".*?"version":\s*"(v[\d.]+)"'), "version", 1, 2),
    # D3 personal assistant
    (re.compile(r'usual room is (Room \d+[A-Z])'), "usual_room", "user", 1),
    (re.compile(r'usual meeting time is (\d\d:\d\d)'), "usual_time", "user", 1),
    (re.compile(r'dinner with (\w+) at (.+? on \w+ at \d\d:\d\d)'), "dinner", 1, 2),
)


def extract_merit_facts(transcript: str) -> list[Fact]:
    """Extract deterministic update keys used by the official MERIT C4 arm."""
    facts: list[Fact] = []
    seen: set[tuple[str, str]] = set()
    for pattern, attribute, entity_group, value_group in _FACT_PATTERNS:
        for match in pattern.finditer(transcript):
            entity = entity_group if isinstance(entity_group, str) else match.group(entity_group)
            value = match.group(value_group)
            key = f"{entity}.{attribute}"
            item = (key, value)
            if item not in seen:
                seen.add(item)
                facts.append(Fact(*item))
    return facts


@dataclass
class AutoMemMemory:
    """Duck-typed implementation of MERIT's ``MemoryBase`` interface."""

    endpoint: str = "http://localhost:8001"
    token: str = "test-token"
    variant: Variant = "plain"
    run_tag: str | None = None
    recall_limit: int = 8
    allow_remote: bool = False
    request: HttpRequest | None = None
    name: str = field(init=False)
    meter: dict[str, int] = field(init=False)
    metering: MeteringSnapshot = field(default_factory=MeteringSnapshot, init=False)
    _latest_by_key: dict[str, tuple[str, str]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.variant not in {"plain", "supersede-on-write"}:
            raise ValueError(f"unknown MERIT AutoMem variant: {self.variant}")
        if not self.allow_remote and not is_local_endpoint(self.endpoint):
            raise ValueError("MERIT adapter refuses non-local endpoint; pass allow_remote=True explicitly")
        self.endpoint = self.endpoint.rstrip("/")
        self.run_tag = self.run_tag or f"merit-run-{int(time.time())}-{secrets.token_hex(4)}"
        self.name = f"automem_{self.variant.replace('-', '_')}"
        # The official runner expects numeric counters.  These only contain
        # server-reported usage; estimates are available in ``metering``.
        self.meter = {"prompt_tokens": 0, "completion_tokens": 0, "embedding_tokens": 0}

    def write(self, episode_id: str, transcript: str) -> None:
        facts = extract_merit_facts(transcript) or [Fact(f"episode.{episode_id}", transcript)]
        for fact in facts:
            payload: dict[str, Any] = {
                "content": f"MERIT {fact.key} = {fact.value} (episode {episode_id})",
                "type": "Context",
                "tags": [self.run_tag, "merit", "merit-fact", fact.key],
                "metadata": {
                    "merit_episode_id": episode_id,
                    "merit_fact_key": fact.key,
                    "merit_fact_value": fact.value,
                    "merit_variant": self.variant,
                },
            }
            previous = self._latest_by_key.get(fact.key)
            if self.variant == "supersede-on-write" and previous and previous[1] != fact.value:
                payload["supersedes_memory_id"] = previous[0]
                payload["supersede_relation"] = "INVALIDATED_BY"
            response = self._call("POST", "/memory", payload)
            memory_id = response.get("memory_id") or response.get("id")
            if not isinstance(memory_id, str) or not memory_id:
                raise RuntimeError("AutoMem /memory response omitted memory_id")
            self._latest_by_key[fact.key] = (memory_id, fact.value)

    def read(self, current_context: str, budget_chars: int = 4000) -> str:
        query = urlencode(
            [("query", current_context), ("tags", self.run_tag or ""),
             ("limit", str(self.recall_limit)), ("current_only", "true")]
        )
        response = self._call("GET", f"/recall?{query}", None)
        results = response.get("results", [])
        if not isinstance(results, list):
            raise RuntimeError("AutoMem /recall response has non-list results")
        blocks: list[str] = []
        used = 0
        for item in results:
            if not isinstance(item, dict):
                continue
            memory = item.get("memory", item)
            content = memory.get("content") if isinstance(memory, dict) else None
            if not isinstance(content, str) or used + len(content) > budget_chars:
                continue
            blocks.append(content)
            used += len(content)
        return "\n---\n".join(blocks)

    def metering_record(self) -> dict[str, Any]:
        """Return an auditable record suitable for MERIT result metadata."""
        return {
            "run_tag": self.run_tag,
            "variant": self.variant,
            "server_usage_only": self.meter.copy(),
            "http": self.metering.as_dict(),
        }

    def _call(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        response = self.request(method, path, body) if self.request else self._http(method, path, body)
        self.metering.record(body, response)
        usage = response.get("usage") or response.get("metering") or {}
        if isinstance(usage, dict):
            for target, source in (("prompt_tokens", "prompt_tokens"),
                                   ("completion_tokens", "completion_tokens"),
                                   ("embedding_tokens", "embedding_tokens")):
                if isinstance(usage.get(source), (int, float)):
                    self.meter[target] += int(usage[source])
        return response

    def _http(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = Request(
            f"{self.endpoint}{path}", data=data, method=method,
            headers={"X-Api-Key": self.token, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:  # nosec B310: endpoint guarded above
            parsed = json.loads(response.read())
        if not isinstance(parsed, dict):
            raise RuntimeError(f"AutoMem {method} {path} returned non-object JSON")
        return parsed
