#!/usr/bin/env python3
"""Deterministic BEAM retrieval-proxy harness for AutoMem.

This runner is intentionally narrower than upstream BEAM. It seeds BEAM chats
into AutoMem as small chronological memories, probes /recall with BEAM
questions, and scores retrieval evidence deterministically. It does not
generate answers or run a judge, so its scores are retrieval-proxy context, not
official BEAM end-to-end benchmark numbers.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import pathlib
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINT = "http://localhost:8001"
DEFAULT_TOKEN = os.environ.get(
    "AUTOMEM_API_TOKEN",
    os.environ.get("LOCAL_AUTOMEM_API_TOKEN", "test-token"),
)
DEFAULT_OUTPUT_DIR = REPO / "data" / "results" / "beam-retrieval"
DEFAULT_CACHE_DIR = REPO / "third_party" / "memory-benchmarks" / "datasets" / "beam"
MAX_MEMORY_CHARS = 500
DEFAULT_RECALL_LIMIT = 50
BATCH_LIMIT = 500

BEAM_QUESTION_TYPES: tuple[str, ...] = (
    "abstention",
    "contradiction_resolution",
    "event_ordering",
    "information_extraction",
    "instruction_following",
    "knowledge_update",
    "multi_session_reasoning",
    "preference_following",
    "summarization",
    "temporal_reasoning",
)

BEAM_QUESTION_TYPE_DESCRIPTIONS: dict[str, str] = {
    "abstention": "Withholding answers when evidence is absent from the conversation",
    "contradiction_resolution": "Detecting and reconciling inconsistent statements across dialogue turns",
    "event_ordering": "Reconstructing the chronological sequence of events and developments",
    "information_extraction": "Recalling specific entities, dates, numbers, and factual details",
    "instruction_following": "Sustained adherence to user-specified constraints and formatting preferences",
    "knowledge_update": "Revising stored facts when new or corrected information appears",
    "multi_session_reasoning": "Integrating evidence scattered across non-adjacent dialogue segments",
    "preference_following": "Adapting responses to evolving user preferences and personal choices",
    "summarization": "Abstracting and compressing dialogue content into concise summaries",
    "temporal_reasoning": "Reasoning about explicit and implicit time relations, durations, and sequences",
}

class AutoMemRequestError(RuntimeError):
    def __init__(self, status: int, reason: str, body: str):
        self.status = status
        self.reason = reason
        self.body = body
        super().__init__(f"AutoMem HTTP {status} {reason}: {body}")


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "based",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "information",
    "is",
    "it",
    "me",
    "mention",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "present",
    "provided",
    "related",
    "response",
    "should",
    "that",
    "the",
    "there",
    "this",
    "to",
    "user",
    "was",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class DatasetSpec:
    tier: str
    repo: str
    split: str
    cache_name: str


@dataclass(frozen=True)
class BeamQuestion:
    question_id: str
    question_type: str
    question: str
    rubric: list[str]
    source_chat_ids: list[int]
    difficulty: str = "unknown"


@dataclass(frozen=True)
class BeamConversation:
    tier: str
    conversation_idx: int
    conversation_id: str
    conversation_tag: str
    chat: list[list[dict[str, Any]]]
    questions: list[BeamQuestion]


@dataclass(frozen=True)
class MemoryChunk:
    key: str
    content: str
    tags: list[str]
    metadata: dict[str, Any]
    sequence: int
    conversation_id: str


def normalize_tier(value: str) -> str:
    raw = (value or "").strip()
    key = raw.upper()
    aliases = {
        "100K": "100K",
        "128K": "100K",
        "500K": "500K",
        "1M": "1M",
        "10M": "10M",
    }
    if key not in aliases:
        raise ValueError(
            f"unsupported BEAM tier {value!r}; expected one of 100k, 128k, 500k, 1m, 10m"
        )
    return aliases[key]


def dataset_spec_for_tier(value: str) -> DatasetSpec:
    tier = normalize_tier(value)
    repo = "Mohammadta/BEAM-10M" if tier == "10M" else "Mohammadta/BEAM"
    return DatasetSpec(
        tier=tier,
        repo=repo,
        split=tier,
        cache_name=f"beam_{tier}.json",
    )


def _parse_http_endpoint(endpoint: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid endpoint; expected absolute http(s) URL: {endpoint}")
    return parsed


def is_local_endpoint(endpoint: str) -> bool:
    parsed = _parse_http_endpoint(endpoint)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def assert_endpoint_allowed(endpoint: str, allow_non_local: bool) -> None:
    if allow_non_local or is_local_endpoint(endpoint):
        return
    raise SystemExit(f"refusing non-local endpoint without --allow-non-local: {endpoint}")


def run_tag(run_id: str) -> str:
    return run_id if run_id.startswith("beam-run-") else f"beam-run-{run_id}"


def tier_tag(tier: str) -> str:
    return f"beam-tier-{normalize_tier(tier).lower()}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "unknown"


def conversation_tag(conversation_id: str) -> str:
    return f"beam-conv-{slugify(conversation_id)}"


def parse_probing_questions(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    for parser in (ast.literal_eval, json.loads):
        try:
            parsed = parser(raw)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _unwrap_batch_dicts(batch_dicts: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    for batch in batch_dicts:
        turns = batch.get("turns", [])
        flat_turns: list[dict[str, Any]] = []
        for item in turns:
            if isinstance(item, list):
                flat_turns.extend(t for t in item if isinstance(t, dict))
            elif isinstance(item, dict):
                flat_turns.append(item)
        batches.append(flat_turns)
    return batches


def parse_beam_chat(chat_data: Any) -> list[list[dict[str, Any]]]:
    if not chat_data:
        return []

    if (
        isinstance(chat_data, list)
        and chat_data
        and isinstance(chat_data[0], dict)
        and "turns" in chat_data[0]
    ):
        return _unwrap_batch_dicts(chat_data)

    if (
        isinstance(chat_data, list)
        and chat_data
        and isinstance(chat_data[0], dict)
        and "turns" not in chat_data[0]
    ):
        first = chat_data[0]
        sample_val = next(iter(first.values()), None)
        is_plan_format = (
            isinstance(sample_val, list)
            and sample_val
            and isinstance(sample_val[0], dict)
            and "turns" in sample_val[0]
        )
        if is_plan_format:
            batches: list[list[dict[str, Any]]] = []
            for session in chat_data:
                if not isinstance(session, dict):
                    continue
                plan_keys = sorted(
                    session.keys(),
                    key=lambda k: int(str(k).split("-")[-1])
                    if str(k).split("-")[-1].isdigit()
                    else 0,
                )
                for plan_key in plan_keys:
                    plan_batches = session.get(plan_key)
                    if plan_batches:
                        batches.extend(_unwrap_batch_dicts(plan_batches))
            return batches

        if "role" in first or "content" in first:
            return [chat_data]
        return []

    if isinstance(chat_data, list) and chat_data and isinstance(chat_data[0], list):
        return [
            [turn for turn in batch if isinstance(turn, dict)]
            for batch in chat_data
            if isinstance(batch, list)
        ]

    return []


def extract_source_chat_ids(question_data: dict[str, Any]) -> list[int]:
    values = [
        question_data.get("source_chat_ids"),
        question_data.get("conversation_references"),
    ]
    found: set[int] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            found.add(value)
            return
        if isinstance(value, str):
            for match in re.finditer(r"chat_id\s*:\s*(\d+)", value, flags=re.I):
                found.add(int(match.group(1)))
            return
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list | tuple | set):
            for child in value:
                visit(child)

    for item in values:
        visit(item)
    return sorted(found)


def extract_rubric_nuggets(question_data: dict[str, Any]) -> list[str]:
    rubric_raw = question_data.get("rubric", [])
    if isinstance(rubric_raw, dict):
        nuggets = rubric_raw.get("nuggets", [])
        return [
            str(nugget.get("description", "")).strip()
            if isinstance(nugget, dict)
            else str(nugget).strip()
            for nugget in nuggets
            if str(nugget).strip()
        ]
    if isinstance(rubric_raw, list):
        return [str(nugget).strip() for nugget in rubric_raw if str(nugget).strip()]
    if rubric_raw:
        return [str(rubric_raw).strip()]
    return []


def normalize_conversation(
    row: dict[str, Any],
    *,
    tier: str,
    conversation_idx: int,
) -> BeamConversation:
    canonical_tier = normalize_tier(tier)
    conversation_id = str(row.get("conversation_id") or f"{canonical_tier}_{conversation_idx}")
    chat = parse_beam_chat(row.get("chat", []))
    probing_questions = parse_probing_questions(row.get("probing_questions", {}))
    questions: list[BeamQuestion] = []

    for question_type in BEAM_QUESTION_TYPES:
        raw_questions = probing_questions.get(question_type, [])
        if isinstance(raw_questions, dict):
            raw_questions = [raw_questions]
        if isinstance(raw_questions, str):
            raw_questions = [{"question": raw_questions, "rubric": []}]
        if not isinstance(raw_questions, list):
            continue

        for raw_question in raw_questions:
            if isinstance(raw_question, str):
                question_data: dict[str, Any] = {"question": raw_question, "rubric": []}
            elif isinstance(raw_question, dict):
                question_data = dict(raw_question)
            else:
                continue

            qi = len(questions)
            question = (
                question_data.get("question_text")
                or question_data.get("question")
                or question_data.get("prompt")
                or ""
            )
            questions.append(
                BeamQuestion(
                    question_id=f"{canonical_tier}_{conversation_idx}_q{qi}_{question_type}",
                    question_type=question_type,
                    question=str(question),
                    rubric=extract_rubric_nuggets(question_data),
                    source_chat_ids=extract_source_chat_ids(question_data),
                    difficulty=str(question_data.get("difficulty", "unknown")),
                )
            )

    return BeamConversation(
        tier=canonical_tier,
        conversation_idx=conversation_idx,
        conversation_id=conversation_id,
        conversation_tag=conversation_tag(conversation_id),
        chat=chat,
        questions=questions,
    )


def _memory_tags(run_id: str, tier: str, conv_tag: str) -> list[str]:
    return ["beam", run_tag(run_id), tier_tag(tier), conv_tag]


def _split_with_prefix(prefix: str, text: str, max_chars: int) -> list[str]:
    if len(prefix) >= max_chars:
        prefix = prefix[: max(0, max_chars - 20)] + " ... "
    payload_budget = max(1, max_chars - len(prefix))
    parts = []
    for start in range(0, len(text), payload_budget):
        part = prefix + text[start : start + payload_budget]
        parts.append(part[:max_chars])
    return parts or [prefix.strip()[:max_chars]]


def build_memory_chunks(
    conversation: BeamConversation,
    *,
    run_id: str,
    max_chars: int = MAX_MEMORY_CHARS,
) -> list[MemoryChunk]:
    chunks: list[MemoryChunk] = []
    sequence = 0
    tags = _memory_tags(run_id, conversation.tier, conversation.conversation_tag)
    fallback_chat_id = 0

    for batch_idx, batch in enumerate(conversation.chat):
        for turn_idx, turn in enumerate(batch):
            content = str(turn.get("content") or "").strip()
            if not content:
                continue
            chat_id_raw = turn.get("id", fallback_chat_id)
            fallback_chat_id += 1
            try:
                chat_id = int(chat_id_raw)
            except (TypeError, ValueError):
                chat_id = fallback_chat_id
            role = str(turn.get("role") or "user")
            time_anchor = turn.get("time_anchor")
            prefix = (
                f"[BEAM {conversation.tier} conv={conversation.conversation_id} "
                f"chat_id={chat_id} role={role}"
            )
            if time_anchor:
                prefix += f" time_anchor={time_anchor}"
            prefix += "] "

            for part_idx, chunk_content in enumerate(
                _split_with_prefix(prefix, content, max_chars)
            ):
                metadata = {
                    "bench": "beam",
                    "runner": "beam-retrieval-proxy",
                    "tier": conversation.tier,
                    "conversation_id": conversation.conversation_id,
                    "conversation_idx": conversation.conversation_idx,
                    "source_chat_ids": [chat_id],
                    "chat_id": chat_id,
                    "role": role,
                    "batch_idx": batch_idx,
                    "turn_idx": turn_idx,
                    "chunk_part": part_idx,
                    "sequence": sequence,
                }
                if time_anchor:
                    metadata["time_anchor"] = time_anchor
                chunks.append(
                    MemoryChunk(
                        key=(
                            f"{conversation.conversation_id}:"
                            f"{batch_idx}:{turn_idx}:{part_idx}"
                        ),
                        content=chunk_content,
                        tags=list(tags),
                        metadata=metadata,
                        sequence=sequence,
                        conversation_id=conversation.conversation_id,
                    )
                )
                sequence += 1

    return chunks


def _json_request(
    endpoint: str,
    token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    flat: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            flat.extend((key, str(item)) for item in value)
        elif isinstance(value, bool):
            flat.append((key, "true" if value else "false"))
        else:
            flat.append((key, str(value)))
    qs = urllib.parse.urlencode(flat)
    url = f"{endpoint.rstrip('/')}{path}"
    if qs:
        url = f"{url}?{qs}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Api-Key": token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise AutoMemRequestError(exc.code, exc.reason, body_text) from exc
    return json.loads(raw) if raw else {}


class AutoMemClient:
    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        request_json: Callable[..., dict[str, Any]] = _json_request,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.request_json = request_json

    def health(self) -> dict[str, Any]:
        return self.request_json(self.endpoint, self.token, "GET", "/health", timeout=10)

    def store_memory_batch(
        self,
        chunks: list[MemoryChunk],
        *,
        batch_size: int = BATCH_LIMIT,
    ) -> list[str]:
        memory_ids: list[str] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            body = {
                "memories": [
                    {
                        "content": chunk.content,
                        "tags": chunk.tags,
                        "importance": 0.7,
                        "type": "Context",
                        "confidence": 0.9,
                        "metadata": chunk.metadata,
                    }
                    for chunk in batch
                ]
            }
            response = self.request_json(
                self.endpoint,
                self.token,
                "POST",
                "/memory/batch",
                body=body,
                timeout=120,
            )
            returned_ids = response.get("memory_ids") or response.get("ids") or []
            if len(returned_ids) != len(batch):
                raise RuntimeError(
                    "AutoMem /memory/batch returned "
                    f"{len(returned_ids)} ids for {len(batch)} memories"
                )
            memory_ids.extend(str(memory_id) for memory_id in returned_ids)
        return memory_ids

    def associate_sequential_chunks(
        self,
        memory_ids: list[str],
        *,
        batch_size: int = BATCH_LIMIT,
    ) -> int:
        associations = [
            {
                "memory1_id": left,
                "memory2_id": right,
                "type": "OCCURRED_BEFORE",
                "strength": 0.9,
            }
            for left, right in zip(memory_ids, memory_ids[1:], strict=False)
            if left and right and left != right
        ]
        created = 0
        for start in range(0, len(associations), batch_size):
            batch = associations[start : start + batch_size]
            try:
                response = self.request_json(
                    self.endpoint,
                    self.token,
                    "POST",
                    "/associate",
                    body={"associations": batch},
                    timeout=120,
                )
            except AutoMemRequestError as exc:
                if exc.status not in {400, 404, 405}:
                    raise
                created += self._associate_single_fallback(batch)
                continue
            created += int(response.get("created_count", len(batch)))
        return created

    def _associate_single_fallback(self, associations: list[dict[str, Any]]) -> int:
        created = 0
        for association in associations:
            self.request_json(
                self.endpoint,
                self.token,
                "POST",
                "/associate",
                body=association,
                timeout=60,
            )
            created += 1
        return created

    def recall_question(
        self,
        question: BeamQuestion,
        *,
        run_id: str,
        conv_tag: str,
        limit: int,
    ) -> dict[str, Any]:
        return self.request_json(
            self.endpoint,
            self.token,
            "GET",
            "/recall",
            params={
                "query": question.question,
                "tags": [run_tag(run_id), conv_tag],
                "tag_mode": "all",
                "tag_match": "exact",
                "limit": limit,
            },
            timeout=60,
        )

    def cleanup_run(self, run_id: str) -> int:
        deleted = 0
        tag = run_tag(run_id)
        deleted_ids: set[str] = set()
        stale_rounds = 0
        while True:
            response = self.request_json(
                self.endpoint,
                self.token,
                "GET",
                "/recall",
                params={
                    "query": "",
                    "tags": [tag],
                    "tag_match": "exact",
                    "limit": BATCH_LIMIT,
                },
                timeout=60,
            )
            results = response.get("results") or []
            if not results:
                break
            page_ids = [memory_id for result in results if (memory_id := result_id(result))]
            new_ids = [memory_id for memory_id in page_ids if memory_id not in deleted_ids]
            if not new_ids:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
                time.sleep(0.2)
                continue
            stale_rounds = 0
            for memory_id in new_ids:
                self.request_json(
                    self.endpoint,
                    self.token,
                    "DELETE",
                    f"/memory/{urllib.parse.quote(memory_id)}",
                    timeout=30,
                )
                deleted_ids.add(memory_id)
                deleted += 1
        return deleted


def result_id(result: dict[str, Any]) -> str | None:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    for value in (
        result.get("id"),
        result.get("memory_id"),
        memory.get("id"),
        memory.get("memory_id"),
    ):
        if value:
            return str(value)
    return None


def result_content(result: dict[str, Any]) -> str:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    return str(memory.get("content") or result.get("content") or result.get("memory") or "")


def result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    memory = result.get("memory") if isinstance(result.get("memory"), dict) else {}
    metadata = memory.get("metadata") or result.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _tokens(text: str) -> set[str]:
    normalized = text.lower().replace("-", " ").replace("_", " ")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in STOPWORDS and len(token) > 1
    }


def score_rubric_overlap(rubric: list[str], evidence_texts: list[str]) -> float:
    if not rubric:
        return 0.0
    evidence_tokens = [_tokens(text) for text in evidence_texts]
    scores: list[float] = []
    for nugget in rubric:
        nugget_tokens = _tokens(nugget)
        if not nugget_tokens:
            scores.append(0.0)
            continue
        best = 0.0
        for tokens in evidence_tokens:
            if not tokens:
                continue
            best = max(best, len(nugget_tokens & tokens) / len(nugget_tokens))
        scores.append(best)
    return round(statistics.mean(scores), 4) if scores else 0.0


def score_abstention_evidence_absence(
    rubric: list[str],
    evidence_texts: list[str],
    *,
    threshold: float = 0.25,
) -> bool:
    if not evidence_texts:
        return True
    return score_rubric_overlap(rubric, evidence_texts) < threshold


def _source_ids_from_result(result: dict[str, Any]) -> set[int]:
    metadata = result_metadata(result)
    found = set(extract_source_chat_ids({"source_chat_ids": metadata.get("source_chat_ids")}))
    if not found and metadata.get("chat_id") is not None:
        try:
            found.add(int(metadata["chat_id"]))
        except (TypeError, ValueError):
            pass
    if not found:
        found.update(extract_source_chat_ids({"conversation_references": result_content(result)}))
    return found


def score_question(
    question: BeamQuestion,
    recall_response: dict[str, Any],
) -> dict[str, Any]:
    results = recall_response.get("results") or []
    evidence_texts = [result_content(result) for result in results]
    expected_sources = set(question.source_chat_ids)
    retrieved_sources: set[int] = set()
    for result in results:
        retrieved_sources.update(_source_ids_from_result(result))
    source_hit: bool | None = None
    if expected_sources:
        source_hit = bool(expected_sources & retrieved_sources)

    rubric_overlap = score_rubric_overlap(question.rubric, evidence_texts)
    abstention_absent: bool | None = None
    if question.question_type == "abstention":
        abstention_absent = score_abstention_evidence_absence(question.rubric, evidence_texts)

    if question.question_type == "abstention":
        proxy_score = 1.0 if abstention_absent else 0.0
    elif source_hit is None:
        proxy_score = rubric_overlap
    else:
        proxy_score = (1.0 if source_hit else 0.0) * 0.6 + rubric_overlap * 0.4

    ranked_ids = [result_id(result) for result in results if result_id(result)]
    return {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "question": question.question,
        "rubric": question.rubric,
        "source_chat_ids": question.source_chat_ids,
        "retrieval": {
            "returned": len(results),
            "top_ids": ranked_ids[:10],
            "retrieved_source_chat_ids": sorted(retrieved_sources),
        },
        "metrics": {
            "source_chat_hit": source_hit,
            "rubric_overlap": rubric_overlap,
            "abstention_evidence_absent": abstention_absent,
            "proxy_score": round(proxy_score, 4),
            "passed": proxy_score >= 0.5,
        },
    }


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 4)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 4)


def aggregate_results(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for question_type in BEAM_QUESTION_TYPES:
        rows = [row for row in evaluations if row.get("question_type") == question_type]
        source_hits = [
            row["metrics"]["source_chat_hit"]
            for row in rows
            if row.get("metrics", {}).get("source_chat_hit") is not None
        ]
        abstention = [
            row["metrics"]["abstention_evidence_absent"]
            for row in rows
            if row.get("metrics", {}).get("abstention_evidence_absent") is not None
        ]
        proxy_scores = [row["metrics"]["proxy_score"] for row in rows]
        rubric_scores = [row["metrics"]["rubric_overlap"] for row in rows]
        passed = [row["metrics"]["passed"] for row in rows]
        by_type[question_type] = {
            "description": BEAM_QUESTION_TYPE_DESCRIPTIONS[question_type],
            "total": len(rows),
            "pass_rate": _rate(passed),
            "mean_proxy_score": _mean(proxy_scores),
            "mean_rubric_overlap": _mean(rubric_scores),
            "source_chat_hit_rate": _rate(source_hits),
            "source_chat_hit_denominator": len(source_hits),
            "abstention_evidence_absence_rate": _rate(abstention),
            "abstention_denominator": len(abstention),
        }

    all_proxy = [row["metrics"]["proxy_score"] for row in evaluations]
    all_rubric = [row["metrics"]["rubric_overlap"] for row in evaluations]
    all_passed = [row["metrics"]["passed"] for row in evaluations]
    all_source_hits = [
        row["metrics"]["source_chat_hit"]
        for row in evaluations
        if row.get("metrics", {}).get("source_chat_hit") is not None
    ]
    all_abstention = [
        row["metrics"]["abstention_evidence_absent"]
        for row in evaluations
        if row.get("metrics", {}).get("abstention_evidence_absent") is not None
    ]
    return {
        "overall": {
            "total_questions": len(evaluations),
            "pass_rate": _rate(all_passed),
            "mean_proxy_score": _mean(all_proxy),
            "mean_rubric_overlap": _mean(all_rubric),
            "source_chat_hit_rate": _rate(all_source_hits),
            "source_chat_hit_denominator": len(all_source_hits),
            "abstention_evidence_absence_rate": _rate(all_abstention),
            "abstention_denominator": len(all_abstention),
        },
        "by_question_type": by_type,
    }


def load_beam_rows(
    tier: str,
    *,
    cache_dir: pathlib.Path = DEFAULT_CACHE_DIR,
    dataset_json: pathlib.Path | None = None,
    no_download: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = dataset_spec_for_tier(tier)
    if dataset_json:
        return json.loads(dataset_json.read_text()), {
            "source": "json",
            "path": str(dataset_json),
            "repo": spec.repo,
            "split": spec.split,
        }

    cache_path = cache_dir / spec.cache_name
    if cache_path.exists():
        return json.loads(cache_path.read_text()), {
            "source": "cache",
            "path": str(cache_path),
            "repo": spec.repo,
            "split": spec.split,
        }

    if no_download:
        raise SystemExit(
            f"BEAM {spec.tier} cache not found at {cache_path}; rerun without --no-download "
            "or pass --dataset-json"
        )

    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            f"BEAM {spec.tier} cache not found at {cache_path}. Install the optional "
            "upstream BEAM dependency (`datasets>=2.14`) or pass --dataset-json."
        ) from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset(spec.repo, split=spec.split)
    rows = [dict(item) for item in ds]
    cache_path.write_text(json.dumps(rows, ensure_ascii=False))
    return rows, {
        "source": "huggingface",
        "path": str(cache_path),
        "repo": spec.repo,
        "split": spec.split,
    }


def select_conversations(
    rows: list[dict[str, Any]],
    *,
    tier: str,
    sample_conversations: int | None,
) -> list[BeamConversation]:
    selected = rows[:sample_conversations] if sample_conversations is not None else rows
    return [
        normalize_conversation(row, tier=tier, conversation_idx=idx)
        for idx, row in enumerate(selected)
    ]


def new_run_id() -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def _manifest_conversation(
    conversation: BeamConversation,
    *,
    chunks: list[MemoryChunk],
    memory_ids: list[str],
) -> dict[str, Any]:
    return {
        "tier": conversation.tier,
        "conversation_idx": conversation.conversation_idx,
        "conversation_id": conversation.conversation_id,
        "conversation_tag": conversation.conversation_tag,
        "memory_count": len(memory_ids),
        "memory_ids": memory_ids,
        "chunks": [
            {
                "key": chunk.key,
                "memory_id": memory_ids[idx],
                "sequence": chunk.sequence,
                "source_chat_ids": chunk.metadata.get("source_chat_ids", []),
            }
            for idx, chunk in enumerate(chunks)
        ],
        "questions": [asdict(question) for question in conversation.questions],
    }


def ingest_conversations(
    conversations: list[BeamConversation],
    *,
    client: AutoMemClient,
    run_id: str,
    dataset_info: dict[str, Any],
) -> dict[str, Any]:
    manifest_conversations = []
    total_memories = 0
    total_associations = 0
    for conversation in conversations:
        chunks = build_memory_chunks(conversation, run_id=run_id)
        memory_ids = client.store_memory_batch(chunks)
        total_associations += client.associate_sequential_chunks(memory_ids)
        total_memories += len(memory_ids)
        manifest_conversations.append(
            _manifest_conversation(
                conversation,
                chunks=chunks,
                memory_ids=memory_ids,
            )
        )

    return {
        "schema": "automem-evals.beam-retrieval-manifest.v1",
        "run_id": run_id,
        "run_tag": run_tag(run_id),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dataset": dataset_info,
        "runner": "beam-retrieval-proxy",
        "official_beam_score": False,
        "scoring_note": "Deterministic AutoMem /recall proxy; no answer generation or LLM judge.",
        "memory_count": total_memories,
        "association_count": total_associations,
        "conversations": manifest_conversations,
    }


def manifest_questions(manifest: dict[str, Any]) -> list[tuple[str, BeamQuestion]]:
    questions: list[tuple[str, BeamQuestion]] = []
    for conversation in manifest.get("conversations", []):
        conv_tag = conversation["conversation_tag"]
        for raw_question in conversation.get("questions", []):
            questions.append(
                (
                    conv_tag,
                    BeamQuestion(
                        question_id=raw_question["question_id"],
                        question_type=raw_question["question_type"],
                        question=raw_question["question"],
                        rubric=list(raw_question.get("rubric") or []),
                        source_chat_ids=list(raw_question.get("source_chat_ids") or []),
                        difficulty=raw_question.get("difficulty", "unknown"),
                    ),
                )
            )
    return questions


def evaluate_manifest(
    manifest: dict[str, Any],
    *,
    client: AutoMemClient,
    question_limit: int | None,
    recall_limit: int,
) -> dict[str, Any]:
    questions = manifest_questions(manifest)
    if question_limit is not None:
        questions = questions[:question_limit]

    evaluations: list[dict[str, Any]] = []
    for conv_tag, question in questions:
        recall_response = client.recall_question(
            question,
            run_id=manifest["run_id"],
            conv_tag=conv_tag,
            limit=recall_limit,
        )
        scored = score_question(question, recall_response)
        evaluations.append(scored)

    return {
        "schema": "automem-evals.beam-retrieval-results.v1",
        "run_id": manifest["run_id"],
        "run_tag": manifest["run_tag"],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner": "beam-retrieval-proxy",
        "official_beam_score": False,
        "scoring_note": "Retrieval/nugget proxy only; Graphonomous/Hindsight comparisons are context, not BEAM parity.",
        "dataset": manifest.get("dataset", {}),
        "conversation_count": len(manifest.get("conversations", [])),
        "memory_count": manifest.get("memory_count", 0),
        "association_count": manifest.get("association_count", 0),
        "recall_limit": recall_limit,
        "evaluations": evaluations,
        "aggregate": aggregate_results(evaluations),
    }


def format_report(results: dict[str, Any]) -> str:
    overall = results.get("aggregate", {}).get("overall", {})
    by_type = results.get("aggregate", {}).get("by_question_type", {})
    dataset = results.get("dataset", {})
    lines = [
        f"# BEAM retrieval-proxy report - {results.get('run_id', 'unknown')}",
        "",
        "This is a deterministic AutoMem /recall proxy, not an official BEAM score.",
        "",
        "## Run",
        "",
        "| field | value |",
        "|---|---|",
        f"| tier | {dataset.get('split', 'unknown')} |",
        f"| source | {dataset.get('source', 'unknown')} |",
        f"| dataset | {dataset.get('repo', 'unknown')} |",
        f"| conversations | {results.get('conversation_count', 0)} |",
        f"| memories | {results.get('memory_count', 0)} |",
        f"| associations | {results.get('association_count', 0)} |",
        f"| recall_limit | {results.get('recall_limit', DEFAULT_RECALL_LIMIT)} |",
        "",
        "## Overall",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| questions | {overall.get('total_questions', 0)} |",
        f"| pass_rate | {_fmt_pct(overall.get('pass_rate'))} |",
        f"| mean_proxy_score | {_fmt_num(overall.get('mean_proxy_score'))} |",
        f"| mean_rubric_overlap | {_fmt_num(overall.get('mean_rubric_overlap'))} |",
        f"| source_chat_hit_rate | {_fmt_pct(overall.get('source_chat_hit_rate'))} |",
        f"| abstention_evidence_absence_rate | {_fmt_pct(overall.get('abstention_evidence_absence_rate'))} |",
        "",
        "## By Ability",
        "",
        "| ability | n | pass | proxy | rubric | source hit | abstention absent |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for question_type in BEAM_QUESTION_TYPES:
        row = by_type.get(question_type, {})
        lines.append(
            f"| {question_type} | {row.get('total', 0)} "
            f"| {_fmt_pct(row.get('pass_rate'))} "
            f"| {_fmt_num(row.get('mean_proxy_score'))} "
            f"| {_fmt_num(row.get('mean_rubric_overlap'))} "
            f"| {_fmt_pct(row.get('source_chat_hit_rate'))} "
            f"| {_fmt_pct(row.get('abstention_evidence_absence_rate'))} |"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- No answerer model or judge model is invoked.",
            "- Source-chat hits are only scored when BEAM question metadata names source chat IDs.",
            "- Rubric overlap is token overlap over retrieved memory text, not semantic judgment.",
            "- Treat Graphonomous/Hindsight numbers as retrieval-proxy context only.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_num(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.4f}"


def _fmt_pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.1f}%"


def _run_dir(output: pathlib.Path, run_id: str) -> pathlib.Path:
    return output / run_id


def _write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def run_ingest(args: argparse.Namespace) -> int:
    assert_endpoint_allowed(args.endpoint, args.allow_non_local)
    tier = normalize_tier(args.tier)
    rid = args.run_id or new_run_id()
    output = pathlib.Path(args.output)
    run_dir = _run_dir(output, rid)
    rows, dataset_info = load_beam_rows(
        tier,
        dataset_json=pathlib.Path(args.dataset_json) if args.dataset_json else None,
        no_download=args.no_download,
    )
    conversations = select_conversations(
        rows,
        tier=tier,
        sample_conversations=args.sample_conversations,
    )
    client = AutoMemClient(args.endpoint, args.token)
    manifest = ingest_conversations(
        conversations,
        client=client,
        run_id=rid,
        dataset_info=dataset_info,
    )
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    print(f"manifest: {manifest_path}")
    if args.cleanup_after:
        deleted = client.cleanup_run(rid)
        print(f"cleanup: deleted {deleted} memories tagged {run_tag(rid)}")
    return 0


def _ingest_for_eval(args: argparse.Namespace) -> tuple[dict[str, Any], pathlib.Path]:
    tier = normalize_tier(args.tier)
    rid = args.run_id or new_run_id()
    output = pathlib.Path(args.output)
    run_dir = _run_dir(output, rid)
    rows, dataset_info = load_beam_rows(
        tier,
        dataset_json=pathlib.Path(args.dataset_json) if args.dataset_json else None,
        no_download=args.no_download,
    )
    conversations = select_conversations(
        rows,
        tier=tier,
        sample_conversations=args.sample_conversations,
    )
    client = AutoMemClient(args.endpoint, args.token)
    manifest = ingest_conversations(
        conversations,
        client=client,
        run_id=rid,
        dataset_info=dataset_info,
    )
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest, manifest_path


def run_eval(args: argparse.Namespace) -> int:
    assert_endpoint_allowed(args.endpoint, args.allow_non_local)
    client = AutoMemClient(args.endpoint, args.token)
    if args.manifest:
        manifest_path = pathlib.Path(args.manifest)
        manifest = json.loads(manifest_path.read_text())
        run_dir = manifest_path.parent
    else:
        manifest, manifest_path = _ingest_for_eval(args)
        run_dir = manifest_path.parent

    results = evaluate_manifest(
        manifest,
        client=client,
        question_limit=args.question_limit,
        recall_limit=args.top_k,
    )
    results_path = run_dir / "results.json"
    _write_json(results_path, results)
    report_path = run_dir / "report.md"
    report_path.write_text(format_report(results))
    print(f"manifest: {manifest_path}")
    print(f"results:  {results_path}")
    print(f"report:   {report_path}")
    if args.cleanup_after:
        deleted = client.cleanup_run(manifest["run_id"])
        print(f"cleanup: deleted {deleted} memories tagged {manifest['run_tag']}")
    return 0


def run_report(args: argparse.Namespace) -> int:
    input_path = pathlib.Path(args.input)
    results = json.loads(input_path.read_text())
    report = format_report(results)
    output_path = pathlib.Path(args.output) if args.output else input_path.with_suffix(".md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"report: {output_path}")
    return 0


def run_cleanup(args: argparse.Namespace) -> int:
    assert_endpoint_allowed(args.endpoint, args.allow_non_local)
    manifest_path = pathlib.Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    client = AutoMemClient(args.endpoint, args.token)
    deleted = client.cleanup_run(manifest["run_id"])
    print(f"cleanup: deleted {deleted} memories tagged {manifest['run_tag']}")
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tier", default="100k", help="100k|128k|500k|1m|10m")
    parser.add_argument("--sample-conversations", type=int, default=None)
    parser.add_argument("--question-limit", type=int, default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cleanup-after", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--dataset-json", default=None)
    parser.add_argument("--top-k", type=int, default=DEFAULT_RECALL_LIMIT)
    parser.add_argument("--allow-non-local", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser("ingest", help="Seed BEAM conversations into AutoMem")
    _add_common_args(ingest)

    evaluate = subcommands.add_parser("eval", help="Run deterministic /recall scoring")
    _add_common_args(evaluate)

    report = subcommands.add_parser("report", help="Render markdown from results JSON")
    report.add_argument("--input", required=True)
    report.add_argument("--output", default=None)

    cleanup = subcommands.add_parser("cleanup", help="Delete memories for an ingest manifest")
    cleanup.add_argument("--manifest", required=True)
    cleanup.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    cleanup.add_argument("--token", default=DEFAULT_TOKEN)
    cleanup.add_argument("--allow-non-local", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            return run_ingest(args)
        if args.command == "eval":
            return run_eval(args)
        if args.command == "report":
            return run_report(args)
        if args.command == "cleanup":
            return run_cleanup(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
