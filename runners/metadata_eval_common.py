from __future__ import annotations

import gzip
import hashlib
import json
import re
import tarfile
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

WHITELIST_FIELDS = (
    "source",
    "source_agent",
    "source_agents",
    "repo",
    "project",
    "tool",
    "surface",
    "applies_to",
    "trigger",
    "provider",
    "model",
    "entities",
)

SKIP_FIELDS = {
    "original_content",
    "enrichment",
    "semantic_neighbors",
    "patterns_detected",
}

MAX_STRING_LENGTH = 96
MAX_ARRAY_LENGTH = 12
DEFAULT_MAX_TAGS_PER_MEMORY = 8


@dataclass(frozen=True)
class MetadataSignal:
    field: str
    value: str
    slug: str
    tag: str


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def slugify_value(value: Any, *, max_length: int = 80) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def _human_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_search_text(value: Any) -> str:
    return _human_text(value).lower()


def humanize_field(field: str) -> str:
    return field.replace(".", " ").replace("_", " ")


def metadata_value_is_hidden(value: Any, content: str, tags: list[str] | tuple[str, ...]) -> bool:
    phrase = normalize_search_text(value)
    if not phrase:
        return False
    content_norm = normalize_search_text(content or "")
    if phrase and phrase in content_norm:
        return False

    value_slug = slugify_value(value)
    for tag in tags or []:
        tag_slug = slugify_value(tag)
        tag_text = normalize_search_text(tag)
        if value_slug and value_slug in tag_slug:
            return False
        if phrase and phrase in tag_text:
            return False
    return True


def _iter_scalar_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and len(stripped) <= MAX_STRING_LENGTH:
            yield stripped
        return
    if isinstance(value, (int, float, bool)) and not isinstance(value, bool):
        yield str(value)
        return
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        if len(values) > MAX_ARRAY_LENGTH:
            return
        for item in values:
            yield from _iter_scalar_values(item)


def _iter_metadata_values(
    metadata: dict[str, Any], *, include_people: bool = False
) -> Iterator[tuple[str, str]]:
    for field in WHITELIST_FIELDS:
        if field in SKIP_FIELDS or field not in metadata:
            continue
        raw = metadata.get(field)
        if field == "entities":
            if not isinstance(raw, dict):
                continue
            for category, values in raw.items():
                category_text = str(category).strip().lower()
                if not category_text or category_text == "people" and not include_people:
                    continue
                if isinstance(values, dict):
                    continue
                for item in _iter_scalar_values(values):
                    yield f"entities.{category_text}", item
            continue
        if isinstance(raw, dict):
            continue
        for item in _iter_scalar_values(raw):
            yield field, item


def extract_metadata_signals(
    memory: dict[str, Any],
    *,
    max_tags: int = DEFAULT_MAX_TAGS_PER_MEMORY,
    include_people: bool = False,
) -> list[MetadataSignal]:
    metadata = parse_metadata(memory.get("metadata"))
    seen: set[str] = set()
    signals: list[MetadataSignal] = []
    for field, value in _iter_metadata_values(metadata, include_people=include_people):
        value_slug = slugify_value(value)
        field_slug = slugify_value(field.replace(".", "-").replace("_", "-"))
        if not value_slug or not field_slug:
            continue
        tag = f"metadata-{field_slug}-{value_slug}"
        if tag in seen:
            continue
        seen.add(tag)
        signals.append(MetadataSignal(field=field, value=value, slug=value_slug, tag=tag))
        if len(signals) >= max_tags:
            break
    return signals


def compact_metadata_excerpt(
    memory: dict[str, Any],
    *,
    max_items: int = DEFAULT_MAX_TAGS_PER_MEMORY,
    include_people: bool = False,
) -> str:
    signals = extract_metadata_signals(
        memory, max_tags=max_items, include_people=include_people
    )
    parts = [f"{signal.field}: {signal.value}" for signal in signals]
    return "; ".join(parts)


def compute_tag_prefixes(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    prefixes: list[str] = []
    for tag in tags or []:
        normalized = str(tag or "").strip().lower()
        if not normalized:
            continue
        parts = [part for part in re.split(r"[:/]", normalized) if part]
        accum: list[str] = []
        for part in parts:
            accum.append(part)
            prefix = ":".join(accum)
            if prefix not in seen:
                seen.add(prefix)
                prefixes.append(prefix)
    return prefixes


def normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return []


def hash_vector(vector: list[Any] | tuple[Any, ...]) -> str:
    normalized = [float(value) for value in vector or []]
    payload = json.dumps(normalized, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _latest_backup_file(root: Path, service: str) -> Path | None:
    directory = root / service
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.json.gz"))
    return files[-1] if files else None


@contextmanager
def resolved_snapshot_dir(snapshot: Path) -> Iterator[Path]:
    snapshot = Path(snapshot)
    if snapshot.is_dir():
        yield snapshot
        return
    if not snapshot.is_file():
        raise FileNotFoundError(f"snapshot not found: {snapshot}")
    if not (snapshot.name.endswith(".tar.gz") or snapshot.name.endswith(".tgz")):
        raise ValueError(f"unsupported snapshot file: {snapshot}")

    with tempfile.TemporaryDirectory(prefix="automem-metadata-snapshot-") as tmp:
        target = Path(tmp)
        root = target.resolve()
        with tarfile.open(snapshot, "r:gz") as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise ValueError(f"unsafe snapshot member: {member.name}")
                destination = (root / member.name).resolve()
                if not destination.is_relative_to(root):
                    raise ValueError(f"unsafe snapshot path: {member.name}")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"unable to read snapshot member: {member.name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source, destination.open("wb") as handle:
                    handle.write(source.read())
        yield target


def load_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"backup JSON must be an object: {path}")
    return data


def read_snapshot_memories(snapshot: Path) -> list[dict[str, Any]]:
    with resolved_snapshot_dir(snapshot) as root:
        graph_file = _latest_backup_file(root, "falkordb")
        qdrant_file = _latest_backup_file(root, "qdrant")
        memories_by_id: dict[str, dict[str, Any]] = {}

        if graph_file:
            graph_data = load_gzip_json(graph_file)
            for node in graph_data.get("nodes") or []:
                labels = node.get("labels") or []
                if "Memory" not in labels:
                    continue
                props = dict(node.get("properties") or {})
                memory_id = str(props.get("id") or "").strip()
                if not memory_id:
                    continue
                props["id"] = memory_id
                props["tags"] = normalize_tags(props.get("tags"))
                props["metadata"] = parse_metadata(props.get("metadata"))
                memories_by_id[memory_id] = props

        if qdrant_file:
            qdrant_data = load_gzip_json(qdrant_file)
            for point in qdrant_data.get("points") or []:
                memory_id = str(point.get("id") or "").strip()
                if not memory_id:
                    continue
                payload = dict(point.get("payload") or {})
                payload["id"] = str(payload.get("id") or memory_id)
                payload["tags"] = normalize_tags(payload.get("tags"))
                payload["metadata"] = parse_metadata(payload.get("metadata"))
                if memory_id not in memories_by_id:
                    memories_by_id[memory_id] = payload
                else:
                    memories_by_id[memory_id].setdefault("_qdrant_payload", payload)

        return sorted(memories_by_id.values(), key=lambda item: str(item.get("id") or ""))
