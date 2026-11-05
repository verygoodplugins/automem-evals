"""AutoMem-backed memory selection for the MemoryCD evaluation harness.

This module is intentionally dependency-free so it can be overlaid on a clean
MemoryCD clone.  It talks to AutoMem's public HTTP API rather than to an MCP
client: POST /memory, POST /associate, and GET /recall.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base_method import BaseMethod


class AutoMemHTTPError(RuntimeError):
    """A compact API error that never includes credentials."""


class AutoMemMethod(BaseMethod):
    """Ingest a user's MemoryCD history into an isolated AutoMem graph.

    Each interaction is stored as a node.  An interaction has a ``PART_OF``
    edge to its per-user/per-domain profile, while those domain profiles have
    pairwise ``RELATES_TO`` edges.  Recall is scoped to the run and user and
    opts into ``expand_relations`` so retrieved seed nodes can traverse the
    cross-domain graph.

    A failed memory request deliberately falls back to recency selection.  It
    records ``last_error`` and writes a terse stderr warning, which preserves
    MemoryCD's usual "one bad provider call does not crash an evaluation"
    behavior without silently claiming a graph-backed result.
    """

    def __init__(
        self,
        max_memory_items: Optional[int] = 10,
        dataset_name: Optional[str] = None,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_seconds: float = 30.0,
        run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_memory_items=max_memory_items, **kwargs)
        self.dataset_name = dataset_name or "memorycd"
        self.api_url = (api_url or os.getenv("AUTOMEM_API_URL") or "http://localhost:8001").rstrip("/")
        self.api_token = api_token if api_token is not None else (
            os.getenv("AUTOMEM_API_TOKEN") or os.getenv("AUTOMEM_API_KEY", "")
        )
        self.timeout_seconds = timeout_seconds
        # A unique tag prevents an experiment from recalling normal operator memories.
        self.run_tag = run_id or f"memorycd-eval-{uuid.uuid4().hex[:12]}"
        self._ingested: Dict[str, Dict[str, str]] = {}
        self.last_error: Optional[str] = None
        self.api_calls: Dict[str, int] = defaultdict(int)

    @staticmethod
    def _short(value: Any, limit: int = 280) -> str:
        text = "" if value is None else str(value).replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 3] + "..."

    @staticmethod
    def _stable_key(interaction: Dict[str, Any], index: int) -> str:
        material = {
            "index": index,
            "asin": interaction.get("parent_asin"),
            "timestamp": interaction.get("timestamp"),
            "rating": interaction.get("rating"),
            "text": interaction.get("text"),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:24]

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self.api_url + path
        if query:
            url += "?" + urlencode(query, doseq=True)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            # AutoMem accepts both forms. Supplying both keeps the overlay
            # compatible with deployments fronted by an API-key proxy.
            headers["X-API-Key"] = self.api_token
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                self.api_calls[f"{method} {path}"] += 1
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise AutoMemHTTPError(f"AutoMem {method} {path} returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AutoMemHTTPError(f"AutoMem {method} {path} failed: {exc}") from exc

    def _store(self, content: str, *, tags: List[str], metadata: Dict[str, Any]) -> str:
        response = self._request(
            "POST",
            "/memory",
            {
                "content": self._short(content, 480),
                "type": "Preference",
                "confidence": 1.0,
                "importance": 0.65,
                "tags": tags,
                "metadata": metadata,
            },
        )
        memory = response.get("memory") if isinstance(response.get("memory"), dict) else response
        memory_id = memory.get("id") or response.get("id") or response.get("memory_id")
        if not memory_id:
            raise AutoMemHTTPError("AutoMem POST /memory returned no memory id")
        return str(memory_id)

    def _associate_many(self, associations: Iterable[Dict[str, Any]]) -> None:
        rows = list(associations)
        if rows:
            self._request("POST", "/associate", {"associations": rows})

    def _domain_for(self, interaction: Dict[str, Any]) -> str:
        return str(interaction.get("domain_category") or self._target_domain() or "unknown")

    def _target_domain(self) -> str:
        return self.dataset_name[6:] if self.dataset_name.startswith("cross_") else self.dataset_name

    def _ingest(self, memory: List[Dict[str, Any]], user_id: str) -> Dict[str, str]:
        fingerprint = hashlib.sha256(
            json.dumps(memory, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        cache_key = f"{user_id}:{fingerprint}"
        if cache_key in self._ingested:
            return self._ingested[cache_key]

        user_tag = f"memorycd-user-{hashlib.sha256(user_id.encode()).hexdigest()[:16]}"
        by_domain: Dict[str, List[tuple[str, Dict[str, Any]]]] = defaultdict(list)
        for index, interaction in enumerate(memory):
            domain = self._domain_for(interaction)
            interaction_key = self._stable_key(interaction, index)
            by_domain[domain].append((interaction_key, interaction))

        domain_ids: Dict[str, str] = {}
        interaction_ids: Dict[str, str] = {}
        for domain, rows in by_domain.items():
            domain_ids[domain] = self._store(
                f"MemoryCD domain profile for user {user_id}: {domain}.",
                tags=["memorycd", self.run_tag, user_tag, f"memorycd-domain-{domain}"],
                metadata={"memorycd_kind": "domain", "memorycd_user": user_id, "memorycd_domain": domain},
            )
            for interaction_key, interaction in rows:
                title = self._short(interaction.get("title") or interaction.get("parent_asin") or "untitled")
                review = self._short(interaction.get("text"))
                rating = interaction.get("rating", "unknown")
                interaction_ids[interaction_key] = self._store(
                    f"MemoryCD review in {domain}: {title}. Rating: {rating}/5. Review: {review}",
                    tags=["memorycd", self.run_tag, user_tag, f"memorycd-domain-{domain}"],
                    metadata={
                        "memorycd_kind": "interaction",
                        "memorycd_user": user_id,
                        "memorycd_domain": domain,
                        "memorycd_interaction_key": interaction_key,
                        "parent_asin": interaction.get("parent_asin"),
                    },
                )

        part_of = []
        for domain, rows in by_domain.items():
            for interaction_key, _ in rows:
                part_of.append(
                    {
                        "memory1_id": interaction_ids[interaction_key],
                        "memory2_id": domain_ids[domain],
                        "type": "PART_OF",
                        "strength": 1.0,
                    }
                )
        self._associate_many(part_of)

        domains = sorted(domain_ids)
        relates_to = []
        for index, domain in enumerate(domains):
            for other_domain in domains[index + 1 :]:
                relates_to.append(
                    {
                        "memory1_id": domain_ids[domain],
                        "memory2_id": domain_ids[other_domain],
                        "type": "RELATES_TO",
                        "strength": 1.0,
                    }
                )
        self._associate_many(relates_to)
        self._ingested[cache_key] = interaction_ids
        return interaction_ids

    def _fallback(self, memory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.max_memory_items is None:
            return memory
        return memory[-self.max_memory_items :]

    def select_memory(
        self,
        memory: List[Dict[str, Any]],
        target_item: Dict[str, Any],
        task: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not memory:
            return []
        user = user_id or "anonymous"
        try:
            interaction_ids = self._ingest(memory, user)
            reverse_ids = {memory_id: interaction_key for interaction_key, memory_id in interaction_ids.items()}
            original = {self._stable_key(item, index): item for index, item in enumerate(memory)}
            target_domain = self._target_domain()
            query = " ".join(
                part
                for part in (
                    f"MemoryCD preference relevant to {target_domain}",
                    self._short(target_item.get("title")),
                    self._short((target_item.get("item_meta") or {}).get("main_category")),
                    self._short((target_item.get("item_meta") or {}).get("description"), 180),
                )
                if part
            )
            user_tag = f"memorycd-user-{hashlib.sha256(user.encode()).hexdigest()[:16]}"
            limit = self.max_memory_items or len(memory)
            response = self._request(
                "GET",
                "/recall",
                query={
                    "query": query,
                    "tags": [self.run_tag, user_tag],
                    "tag_mode": "all",
                    "limit": limit,
                    "expand_relations": "true",
                    "relation_limit": 20,
                    "expansion_limit": max(limit * 3, 10),
                },
            )
            selected: List[Dict[str, Any]] = []
            seen = set()
            for result in response.get("results", []):
                result_id = result.get("id") or (result.get("memory") or {}).get("id")
                key = reverse_ids.get(str(result_id))
                if key is None:
                    key = ((result.get("memory") or {}).get("metadata") or {}).get("memorycd_interaction_key")
                if key in original and key not in seen:
                    selected.append(original[key])
                    seen.add(key)
                if len(selected) >= limit:
                    break
            return selected or self._fallback(memory)
        except AutoMemHTTPError as exc:
            self.last_error = str(exc)
            print(f"Warning: {self.last_error}; using recency fallback", file=sys.stderr)
            return self._fallback(memory)
