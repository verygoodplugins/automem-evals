#!/usr/bin/env python3
"""Build a dashboard index for automem-evals experiment threads."""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import statistics
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("docs/experiments/registry.json")
DEFAULT_STATUS = Path("docs/experiments/STATUS.md")
DEFAULT_INDEX = Path("docs/experiments/index.json")
DEFAULT_SCOREBOARD = Path("docs/experiments/scoreboard.html")

ARTIFACT_ROOTS = [
    Path("data/results"),
    Path("data/sweep_runs"),
    Path("docs"),
]

# Ability buckets are stable across BEAM-judged runs; fixing the order keeps
# the scoreboard's per-ability comparison columns aligned run-to-run.
BEAM_ABILITIES = [
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
]

# Agent Memory Benchmark (AMB) external family. The run config and CI math below
# are mirrored verbatim from runners/amb_aggregate.py (which lives on the
# beam-judged branch, not here) so the scoreboard and that markdown aggregator
# can never report divergent numbers. If you change one, change the other.
DEFAULT_AMB_OUTPUTS = Path("/Users/jgarturo/Projects/OpenAI/agent-memory-benchmark/outputs")
AMB_RUN = "automem-sub"  # canonical single full-split run name
AMB_SINGLE = [
    ("locomo", "locomo10"),
    ("longmemeval", "s"),
    ("personamem", "32k"),
    ("beam", "500k"),
    ("beam", "1m"),
    ("beam", "10m"),
]
# Reproducibility check: BEAM-100K run ×3, reported with across-run spread.
AMB_REPRO = [("beam", "100k", ["automem-sub-rep1", "automem-sub-rep2", "automem-sub-rep3"])]
AMB_LABELS = {
    ("locomo", "locomo10"): "LoCoMo",
    ("longmemeval", "s"): "LongMemEval",
    ("personamem", "32k"): "PersonaMem",
    ("beam", "100k"): "BEAM-100K",
    ("beam", "500k"): "BEAM-500K",
    ("beam", "1m"): "BEAM-1M",
    ("beam", "10m"): "BEAM-10M",
}
AMB_LOW_N = 30  # below this per-question sample count a run is "low_n", not "ok"


def load_registry(root: Path, registry_path: Path | None = None) -> list[dict[str, Any]]:
    path = root / (registry_path or DEFAULT_REGISTRY)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def discover_artifacts(root: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for artifact_root in ARTIFACT_ROOTS:
        base = root / artifact_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = normalize(path.relative_to(root))
            if rel == normalize(DEFAULT_REGISTRY):
                continue
            artifact = summarize_artifact(root, path)
            if artifact:
                artifacts.append(artifact)
    return artifacts


def summarize_artifact(root: Path, path: Path) -> dict[str, Any] | None:
    rel = normalize(path.relative_to(root))
    if rel.endswith(".json") and _is_run_json(rel):
        return summarize_json_artifact(path, rel)
    if rel.endswith(".md") and _is_run_markdown(rel):
        return summarize_markdown_artifact(path, rel)
    return None


def summarize_json_artifact(path: Path, rel: str) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "path": rel,
        "kind": classify_path(rel),
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        artifact["error"] = f"invalid json: {exc}"
        return artifact

    if isinstance(data, dict):
        for key in ("schema", "run_id", "created_at"):
            if key in data:
                artifact[key] = data[key]
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            for key in ("tier", "total_questions", "memory_count", "answerer_model", "judge_model"):
                if key in metadata:
                    artifact[key] = metadata[key]
        metrics = data.get("metrics_by_cutoff")
        if isinstance(metrics, dict):
            overall = _first_overall_metric(metrics)
            if overall:
                artifact["headline_metric"] = overall
        rows = data.get("rows")
        if isinstance(rows, list):
            artifact["row_count"] = len(rows)
    return artifact


def summarize_markdown_artifact(path: Path, rel: str) -> dict[str, Any]:
    title = rel
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    except OSError:
        pass
    return {
        "path": rel,
        "kind": classify_path(rel),
        "title": title,
        "created_at": timestamp_from_path(rel),
    }


def classify_path(rel: str) -> str:
    if "beam-judged/" in rel:
        return "beam-judged"
    if "beam-retrieval/" in rel:
        return "beam-retrieval"
    if rel.endswith("-comparison.md"):
        return "ruleset-comparison"
    if rel.endswith("-recall-endpoint-comparison.md") or "recall-compare/summary.json" in rel:
        return "recall-endpoint-comparison"
    if "-current-state-" in rel:
        return "current-state"
    if "/summary.json" in rel:
        return "summary-json"
    if rel.startswith("docs/session_"):
        return "session-note"
    if rel.startswith("docs/eval/"):
        return "eval-doc"
    if rel.startswith("data/results/SUMMARY-"):
        return "curated-summary"
    return "artifact"


def timestamp_from_path(rel: str) -> str | None:
    match = re.search(r"(\d{8})[-T](\d{6})", rel)
    if not match:
        match = re.search(r"(\d{8})_(\d{6})", rel)
    if not match:
        return None
    date, time = match.groups()
    return f"{date[:4]}-{date[4:6]}-{date[6:8]}T{time[:2]}:{time[2:4]}:{time[4:6]}"


def extract_scores(
    data_root: Path, amb_outputs: Path | None = None
) -> list[dict[str, Any]]:
    """Collect per-run score records from benchmark result trees.

    Structured as a parser registry so additional benchmarks can be slotted in
    without touching callers. ``beam-judged`` is read from ``data_root`` (the
    in-repo results tree); the AMB family is read from ``amb_outputs`` (the
    neutral harness's outputs dir, typically a sibling repo) and is skipped
    entirely when that path is None or absent.
    """
    scores: list[dict[str, Any]] = []
    scores.extend(_parse_beam_judged_scores(data_root))
    scores.extend(_parse_amb_scores(amb_outputs))
    scores.sort(key=lambda record: record.get("created_at") or "")
    return scores


def _parse_beam_judged_scores(data_root: Path) -> list[dict[str, Any]]:
    base = data_root / "data" / "results" / "beam-judged"
    if not base.exists():
        return []
    records: list[dict[str, Any]] = []
    for results_path in sorted(base.glob("*/results.json")):
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cutoff_name, cutoff = _first_cutoff(data.get("metrics_by_cutoff"))
        if not cutoff:
            continue
        overall = cutoff.get("overall", {})
        accuracy = overall.get("accuracy")
        if accuracy is None:
            continue
        metadata = data.get("metadata", {})
        by_ability = {
            ability: bucket.get("accuracy")
            for ability, bucket in (cutoff.get("by_question_type") or {}).items()
            if isinstance(bucket, dict) and bucket.get("accuracy") is not None
        }
        records.append(
            {
                "benchmark": "beam-judged",
                "run_id": data.get("run_id") or results_path.parent.name,
                "created_at": data.get("created_at"),
                "tier": metadata.get("tier"),
                "answerer_model": metadata.get("answerer_model"),
                "judge_model": metadata.get("judge_model"),
                "total_questions": metadata.get("total_questions") or overall.get("total"),
                "cutoff": cutoff_name,
                "accuracy": accuracy,
                "avg_score": overall.get("avg_score"),
                "by_ability": by_ability,
            }
        )
    return records


def _first_cutoff(metrics: Any) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(metrics, dict):
        return None, None
    for name, values in metrics.items():
        if isinstance(values, dict):
            return name, values
    return None, None


def _parse_amb_scores(amb_outputs: Path | None) -> list[dict[str, Any]]:
    """Read AMB harness outputs into per-dataset score records.

    Every configured dataset yields a record; datasets without a canonical run
    on disk are emitted with ``status="missing"`` so the scoreboard can render
    them as "pending" rather than silently dropping coverage gaps.
    """
    if amb_outputs is None:
        return []
    out = Path(amb_outputs)
    if not out.exists():
        return []
    records = [_amb_single_record(out, ds, split) for ds, split in AMB_SINGLE]
    records.extend(_amb_repro_record(out, ds, split, runs) for ds, split, runs in AMB_REPRO)
    return records


def _amb_label(dataset: str, split: str) -> str:
    return AMB_LABELS.get((dataset, split), f"{dataset}/{split}")


def _amb_load(out: Path, dataset: str, run: str, split: str) -> dict[str, Any] | None:
    path = out / dataset / run / "rag" / f"{split}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _amb_per_q_scores(data: dict[str, Any]) -> list[float]:
    """Per-question score in [0,1]: continuous ``score`` if present, else 0/1 ``correct``."""
    values: list[float] = []
    for result in data.get("results", []):
        score = result.get("score")
        values.append(float(score) if score is not None else (1.0 if result.get("correct") else 0.0))
    return values


def _amb_within_run_ci(data: dict[str, Any]) -> tuple[float | None, float | None, int]:
    values = _amb_per_q_scores(data)
    n = len(values)
    if n == 0:
        return None, None, 0
    mean = statistics.mean(values)
    ci = 1.96 * statistics.pstdev(values) / math.sqrt(n)
    return mean, ci, n


def _amb_single_record(out: Path, dataset: str, split: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "benchmark": "amb",
        "dataset": dataset,
        "split": split,
        "label": _amb_label(dataset, split),
        "run_name": AMB_RUN,
        "repeats": 1,
        "spread": None,
        "ci": None,
        "accuracy": None,
        "n": 0,
        "avg_retrieve_time_ms": None,
        "avg_context_tokens": None,
        "answer_llm": None,
        "status": "missing",
    }
    data = _amb_load(out, dataset, AMB_RUN, split)
    if not data:
        return record
    mean, ci, n = _amb_within_run_ci(data)
    if mean is None:
        return record
    # Store raw values; round once at display (matches runners/amb_aggregate.py,
    # which formats raw means with :.1f). Pre-rounding here would double-round.
    record.update(
        accuracy=mean * 100,
        ci=ci * 100 if ci is not None else None,
        n=n,
        avg_retrieve_time_ms=data.get("avg_retrieve_time_ms"),
        avg_context_tokens=data.get("avg_context_tokens"),
        answer_llm=data.get("answer_llm"),
        status="ok" if n >= AMB_LOW_N else "low_n",
    )
    return record


def _amb_repro_record(out: Path, dataset: str, split: str, runs: list[str]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "benchmark": "amb",
        "dataset": dataset,
        "split": split,
        "label": _amb_label(dataset, split),
        "run_name": "+".join(runs),
        "repeats": 0,
        "spread": None,
        "ci": None,
        "accuracy": None,
        "n": 0,
        "avg_retrieve_time_ms": None,
        "avg_context_tokens": None,
        "answer_llm": None,
        "status": "missing",
    }
    loaded = [d for d in (_amb_load(out, dataset, run, split) for run in runs) if d]
    accs = [d["accuracy"] for d in loaded if d.get("accuracy") is not None]
    if not accs:
        return record
    spread = (max(accs) - min(accs)) if len(accs) > 1 else 0.0
    rets = [d["avg_retrieve_time_ms"] for d in loaded if d.get("avg_retrieve_time_ms")]
    toks = [d["avg_context_tokens"] for d in loaded if d.get("avg_context_tokens")]
    record.update(
        accuracy=statistics.mean(accs) * 100,
        spread=spread * 100,
        repeats=len(loaded),
        n=sum(len(d.get("results", [])) for d in loaded),
        avg_retrieve_time_ms=statistics.median(rets) if rets else None,
        avg_context_tokens=statistics.median(toks) if toks else None,
        answer_llm=loaded[0].get("answer_llm"),
        status="ok",
    )
    return record


def match_artifacts(
    registry: list[dict[str, Any]], artifacts: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_thread: dict[str, list[dict[str, Any]]] = {thread["id"]: [] for thread in registry}
    matched_paths: set[str] = set()

    for thread in registry:
        patterns = thread.get("artifacts", [])
        for artifact in artifacts:
            path = artifact["path"]
            if any(path_matches(path, pattern) for pattern in patterns):
                by_thread[thread["id"]].append(artifact)
                matched_paths.add(path)

    orphan_artifacts = [artifact for artifact in artifacts if artifact["path"] not in matched_paths]
    return by_thread, orphan_artifacts


def path_matches(path: str, pattern: str) -> bool:
    path = normalize(path)
    pattern = normalize(pattern)
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def build_index(
    root: Path,
    *,
    data_root: Path | None = None,
    amb_outputs: Path | None = None,
    worktrees: list[dict[str, Any]] | None = None,
    prs: list[dict[str, Any]] | None = None,
    include_vcs: bool = True,
) -> dict[str, Any]:
    data_root = data_root or root
    registry = load_registry(root)
    artifacts = discover_artifacts(data_root)
    artifacts_by_thread, orphan_artifacts = match_artifacts(registry, artifacts)
    scores = extract_scores(data_root, amb_outputs)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()

    if worktrees is None:
        worktrees = read_git_worktrees(root) if include_vcs else []
    if prs is None:
        prs = read_github_prs(root) if include_vcs else []

    classified_worktrees = classify_worktrees(worktrees, prs)
    threads = []
    for thread in registry:
        thread_copy = dict(thread)
        thread_artifacts = artifacts_by_thread.get(thread["id"], [])
        thread_copy["artifact_count"] = len(thread_artifacts)
        thread_copy["artifact_samples"] = [artifact["path"] for artifact in thread_artifacts[:5]]
        thread_copy["worktree_status"] = reconcile_thread_worktree(thread, classified_worktrees)
        threads.append(thread_copy)

    return {
        "schema": "automem-evals.experiment-index.v1",
        "generated_at": now,
        "root": str(root),
        "data_root": str(data_root),
        "threads": threads,
        "status_counts": dict(Counter(thread["status"] for thread in registry)),
        "scores": scores,
        "artifacts": artifacts,
        "orphan_artifacts": orphan_artifacts,
        "worktrees": classified_worktrees,
        "prs": prs,
    }


def classify_worktrees(
    worktrees: list[dict[str, Any]], prs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    prs_by_branch = {pr.get("headRefName"): pr for pr in prs if pr.get("headRefName")}
    classified = []
    for worktree in worktrees:
        item = dict(worktree)
        branch = item.get("branch")
        pr = prs_by_branch.get(branch)
        item["pr"] = pr
        item["cleanup_candidate"] = False
        if pr and pr.get("state") == "MERGED":
            item["status"] = "merged"
            item["cleanup_candidate"] = True
        elif pr and pr.get("state") == "OPEN":
            item["status"] = "open-pr"
        elif branch in {"main", "master"}:
            item["status"] = "primary"
        else:
            item["status"] = "in-flight"
        classified.append(item)
    return classified


def reconcile_thread_worktree(
    thread: dict[str, Any], classified_worktrees: list[dict[str, Any]]
) -> dict[str, Any] | None:
    expected = thread.get("worktree")
    if not expected:
        return None
    expected_suffix = normalize(str(expected)).rstrip("/")
    for worktree in classified_worktrees:
        path = normalize(str(worktree.get("path", ""))).rstrip("/")
        if path.endswith(expected_suffix.lstrip("../")) or path == expected_suffix:
            return {
                "state": worktree.get("status"),
                "path": worktree.get("path"),
                "branch": worktree.get("branch"),
                "cleanup_candidate": worktree.get("cleanup_candidate", False),
            }
    return {"state": "absent", "path": expected, "branch": thread.get("branch")}


def read_git_worktrees(root: Path) -> list[dict[str, Any]]:
    result = run_command(["git", "worktree", "list", "--porcelain"], cwd=root)
    if result is None:
        return []
    worktrees = parse_git_worktree_porcelain(result)
    for worktree in worktrees:
        add_dirty_count(worktree)
    return worktrees


def parse_git_worktree_porcelain(result: str) -> list[dict[str, Any]]:
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in result.splitlines():
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value[:7]
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
    if current:
        worktrees.append(current)
    return worktrees


def add_dirty_count(worktree: dict[str, Any]) -> None:
    path = worktree.get("path")
    if not path:
        worktree["dirty_entries"] = 0
        return
    status = run_command(["git", "status", "--short"], cwd=Path(path))
    worktree["dirty_entries"] = len(status.splitlines()) if status else 0


def read_github_prs(root: Path) -> list[dict[str, Any]]:
    result = run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            "100",
            "--json",
            "number,title,state,headRefName,url,mergedAt,updatedAt",
        ],
        cwd=root,
    )
    if result is None:
        return []
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def render_status(index: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Experiment Status")
    lines.append("")
    lines.append(f"Generated: `{index['generated_at']}`")
    lines.append("")
    lines.append("This file is generated by `python3 scripts/experiment_index.py`.")
    lines.append("Edit `docs/experiments/registry.json` instead of hand-editing this dashboard.")
    lines.append("")

    lines.append("## Thread Overview")
    lines.append("")
    for thread in sorted(index["threads"], key=lambda t: (t.get("status", ""), t.get("updated", "")), reverse=True):
        lines.append(
            f"- `{thread['id']}` **{thread['title']}** - `{thread['status']}`; "
            f"{thread.get('hypothesis', 'No hypothesis recorded')} Decision: {thread.get('decision', 'No decision recorded')} "
            f"Artifacts: {thread.get('artifact_count', 0)}. Updated: `{thread.get('updated', 'unknown')}`."
        )
    lines.append("")

    lines.append("## Lineage")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    for thread in index["threads"]:
        lines.append(f"  {node_id(thread['id'])}[\"{thread['id']}: {escape_label(thread['title'])}\"]")
    for thread in index["threads"]:
        for related in thread.get("related", []):
            if any(other["id"] == related for other in index["threads"]):
                lines.append(f"  {node_id(thread['id'])} --> {node_id(related)}")
    lines.append("```")
    lines.append("")

    in_progress = [thread for thread in index["threads"] if thread.get("status") == "in-progress"]
    lines.append("## In Progress / Needs Decision")
    lines.append("")
    if in_progress:
        for thread in in_progress:
            lines.append(
                f"- `{thread['id']}`: {thread.get('decision', 'No decision recorded')} "
                f"(branch: `{thread.get('branch') or 'n/a'}`, worktree: `{thread.get('worktree') or 'n/a'}`)."
            )
    else:
        lines.append("- No in-progress experiment threads recorded.")
    lines.append("")

    lines.append("## Worktree & Branch Reconciliation")
    lines.append("")
    if index["worktrees"]:
        for worktree in index["worktrees"]:
            pr = worktree.get("pr") or {}
            pr_label = f"PR #{pr.get('number')} `{pr.get('state')}`" if pr else "no PR"
            dirty = worktree.get("dirty_entries", 0)
            cleanup = "cleanup candidate" if worktree.get("cleanup_candidate") else "keep/review"
            lines.append(
                f"- `{worktree.get('branch', 'detached')}` at `{worktree.get('path')}` - "
                f"`{worktree.get('status')}`; {pr_label}; dirty entries: `{dirty}`; {cleanup}."
            )
    else:
        lines.append("- No git worktrees detected or VCS scanning was disabled.")
    registry_worktrees = [
        thread
        for thread in index["threads"]
        if (thread.get("worktree_status") or {}).get("state") == "absent"
    ]
    if registry_worktrees:
        lines.append("")
        lines.append("Registry worktree refs that are not currently present:")
        for thread in registry_worktrees:
            status = thread["worktree_status"]
            lines.append(
                f"- `{thread['id']}` expected `{status.get('path')}` for branch `{status.get('branch')}`."
            )
    lines.append("")

    scores = index.get("scores", [])
    lines.append("## Benchmark Scores")
    lines.append("")
    if scores:
        lines.append("Full interactive view: `docs/experiments/scoreboard.html` (open in a browser).")
        lines.append("")
        latest_by_group: dict[tuple[Any, ...], dict[str, Any]] = {}
        for record in scores:
            if record.get("benchmark") == "amb":
                key = ("amb", record.get("dataset"), record.get("split"))
            else:
                key = (record.get("benchmark"), record.get("tier"), record.get("answerer_model"))
            latest_by_group[key] = record
        for _key, record in sorted(latest_by_group.items(), key=lambda kv: str(kv[0])):
            lines.append(_render_score_line(record))
    else:
        lines.append(
            "- No benchmark score artifacts reachable from the scanned data root. "
            "Run with `--data-root` pointing at the checkout that holds the run results."
        )
    lines.append("")

    lines.append("## Undocumented Runs")
    lines.append("")
    if index["orphan_artifacts"]:
        for artifact in index["orphan_artifacts"][:100]:
            label = artifact.get("title") or artifact.get("schema") or artifact.get("kind")
            lines.append(f"- `{artifact['path']}` - `{artifact.get('kind')}`; {label}")
        if len(index["orphan_artifacts"]) > 100:
            lines.append(f"- ... plus {len(index['orphan_artifacts']) - 100} more.")
    else:
        lines.append("- No orphan run artifacts detected.")
    lines.append("")
    return "\n".join(lines)


def render_scoreboard_html(index: dict[str, Any]) -> str:
    payload = {
        "generated_at": index.get("generated_at"),
        "status_counts": index.get("status_counts", {}),
        "scores": index.get("scores", []),
        "abilities": BEAM_ABILITIES,
        "threads": [
            {
                "id": thread.get("id"),
                "status": thread.get("status"),
                "decision": thread.get("decision"),
                "updated": thread.get("updated"),
                "artifact_count": thread.get("artifact_count", 0),
            }
            for thread in index.get("threads", [])
        ],
    }
    data_json = json.dumps(payload).replace("</", "<\\/")
    return _SCOREBOARD_TEMPLATE.replace("__DATA__", data_json)


def write_outputs(
    index: dict[str, Any],
    status_path: Path,
    index_path: Path,
    scoreboard_path: Path | None = None,
) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(render_status(index), encoding="utf-8")
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if scoreboard_path is not None:
        scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
        scoreboard_path.write_text(render_scoreboard_html(index), encoding="utf-8")


def run_command(args: list[str], cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _is_run_json(rel: str) -> bool:
    name = Path(rel).name
    return name in {"MANIFEST.json", "manifest.json", "results.json", "summary.json"} or rel.endswith(
        "-matrix.json"
    )


def _is_run_markdown(rel: str) -> bool:
    name = Path(rel).name
    if name == "STATUS.md":
        return False
    return (
        rel.startswith("docs/session_")
        or rel.startswith("docs/eval/")
        or rel.startswith("data/results/")
        and name.endswith(".md")
    )


def _render_score_line(record: dict[str, Any]) -> str:
    if record.get("benchmark") == "amb":
        label = record.get("label") or f"{record.get('dataset')}/{record.get('split')}"
        accuracy = record.get("accuracy")
        if record.get("status") != "ok" or not isinstance(accuracy, (int, float)):
            return f"- `amb` {label}: pending (`{record.get('status')}`, n={record.get('n', 0)})."
        if record.get("spread") is not None:
            acc_text = f"{accuracy:.1f}% (spread {record['spread']:.1f}pp, ×{record.get('repeats', 1)})"
        elif record.get("ci") is not None:
            acc_text = f"{accuracy:.1f}% ± {record['ci']:.1f}"
        else:
            acc_text = f"{accuracy:.1f}%"
        ret = record.get("avg_retrieve_time_ms")
        tok = record.get("avg_context_tokens")
        ret_text = f"{round(ret)} ms" if isinstance(ret, (int, float)) else "?"
        tok_text = f"{round(tok)} tok" if isinstance(tok, (int, float)) else "?"
        return f"- `amb` {label}: `{acc_text}` (n={record.get('n')}, recall {ret_text}, {tok_text})."
    accuracy = record.get("accuracy")
    accuracy_text = f"{round(accuracy, 2)}" if isinstance(accuracy, (int, float)) else "n/a"
    return (
        f"- `{record.get('benchmark')}` {record.get('tier') or ''} "
        f"answerer `{record.get('answerer_model') or 'n/a'}`: latest `{accuracy_text}%` "
        f"(run `{record.get('run_id')}`, {record.get('total_questions') or '?'} q)."
    )


def _first_overall_metric(metrics: dict[str, Any]) -> dict[str, Any] | None:
    for cutoff, values in metrics.items():
        if isinstance(values, dict) and isinstance(values.get("overall"), dict):
            overall = dict(values["overall"])
            overall["cutoff"] = cutoff
            return overall
    return None


def node_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def escape_label(text: str) -> str:
    return text.replace('"', "'")


def normalize(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root for registry + outputs")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Repository root to scan for run artifacts/scores (defaults to --root). "
        "Use to read live results from the main checkout while writing into a worktree.",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Registry path relative to root")
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS, help="STATUS.md path relative to root")
    parser.add_argument("--index-json", type=Path, default=DEFAULT_INDEX, help="Index JSON path relative to root")
    parser.add_argument("--scoreboard", type=Path, default=DEFAULT_SCOREBOARD, help="Scoreboard HTML path relative to root")
    parser.add_argument("--no-scoreboard", action="store_true", help="Skip generating the scoreboard HTML")
    parser.add_argument("--no-vcs", action="store_true", help="Skip git/gh worktree and PR reconciliation")
    parser.add_argument(
        "--amb-outputs",
        type=Path,
        default=DEFAULT_AMB_OUTPUTS,
        help="Agent Memory Benchmark outputs dir (neutral harness). Skipped if absent. "
        "Must match runners/amb_aggregate.py's source so the two stay in parity.",
    )
    parser.add_argument("--no-amb", action="store_true", help="Skip AMB benchmark scores")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    data_root = args.data_root.resolve() if args.data_root else root
    amb_outputs = None if args.no_amb else args.amb_outputs
    index = build_index(
        root, data_root=data_root, amb_outputs=amb_outputs, include_vcs=not args.no_vcs
    )
    scoreboard_path = None if args.no_scoreboard else root / args.scoreboard
    write_outputs(index, root / args.status, root / args.index_json, scoreboard_path)
    print(f"Wrote {root / args.status}")
    print(f"Wrote {root / args.index_json}")
    if scoreboard_path is not None:
        print(f"Wrote {scoreboard_path}")
    return 0


_SCOREBOARD_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoMem eval scoreboard</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --stroke: #30363d;
    --text: #e6edf3; --muted: #8b949e; --faint: #6e7681;
    --info: #4aa3ff; --success: #3fb950; --danger: #f85149; --warn: #d29922;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 28px 24px 64px; }
  h1 { font-size: 24px; margin: 0; }
  h2 { font-size: 16px; margin: 28px 0 6px; }
  .sub { color: var(--muted); margin: 4px 0 0; }
  .caption { color: var(--faint); font-size: 12px; margin: 6px 0 0; }
  .panel { background: var(--panel); border: 1px solid var(--stroke); border-radius: 8px; padding: 14px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-top: 18px; }
  .stat { background: var(--panel); border: 1px solid var(--stroke); border-radius: 8px; padding: 12px 14px; }
  .stat .v { font-size: 22px; font-weight: 600; }
  .stat .l { color: var(--muted); font-size: 12px; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--stroke); }
  th { color: var(--muted); font-weight: 600; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .tag { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
    border: 1px solid var(--stroke); color: var(--muted); }
  .tag.adopted { color: var(--success); border-color: var(--success); }
  .tag.in-progress { color: var(--warn); border-color: var(--warn); }
  .tag.parked { color: var(--info); border-color: var(--info); }
  .legend { display: flex; gap: 16px; margin: 8px 0 0; color: var(--muted); font-size: 12px; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
  .note { background: var(--panel); border: 1px solid var(--stroke); border-radius: 8px; padding: 14px; color: var(--muted); }
  code { background: #1f2630; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const data = JSON.parse(document.getElementById("payload").textContent);
const C = { info:"#4aa3ff", success:"#3fb950", danger:"#f85149", warn:"#d29922", muted:"#8b949e", stroke:"#30363d", faint:"#6e7681", text:"#e6edf3" };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const rnd = (v) => v == null ? v : Math.round(v * 100) / 100;
const fix1 = (v) => v == null ? v : Number(v).toFixed(1);  // 1-decimal display, matches runners/amb_aggregate.py

function lineChart(records, refValue) {
  const w = 820, h = 300, padL = 44, padR = 86, padT = 18, padB = 58;
  const ys = records.map(r => r.accuracy);
  let ymin = Math.min(40, Math.floor(Math.min(...ys) / 10) * 10);
  const ymax = 100;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const n = records.length;
  const xAt = (i) => n === 1 ? padL + plotW / 2 : padL + (plotW * i) / (n - 1);
  const yAt = (v) => padT + plotH * (1 - (v - ymin) / (ymax - ymin));
  let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" role="img">';
  for (let t = ymin; t <= ymax; t += 10) {
    const y = yAt(t);
    svg += '<line x1="' + padL + '" y1="' + y + '" x2="' + (w - padR) + '" y2="' + y + '" stroke="' + C.stroke + '" stroke-width="1"/>';
    svg += '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" fill="' + C.faint + '" font-size="11" text-anchor="end">' + t + '</text>';
  }
  if (refValue != null && refValue >= ymin && refValue <= ymax) {
    const y = yAt(refValue);
    svg += '<line x1="' + padL + '" y1="' + y + '" x2="' + (w - padR) + '" y2="' + y + '" stroke="' + C.warn + '" stroke-width="1.5" stroke-dasharray="5 4"/>';
    svg += '<text x="' + (w - padR + 6) + '" y="' + (y + 4) + '" fill="' + C.warn + '" font-size="11">Hindsight ' + refValue + '%</text>';
  }
  let pts = "";
  records.forEach((r, i) => { pts += xAt(i) + "," + yAt(r.accuracy) + " "; });
  svg += '<polyline points="' + pts.trim() + '" fill="none" stroke="' + C.info + '" stroke-width="2"/>';
  records.forEach((r, i) => {
    const x = xAt(i), y = yAt(r.accuracy);
    const col = r.answerer_model && r.answerer_model.indexOf("mini") >= 0 ? C.success : C.info;
    svg += '<circle cx="' + x + '" cy="' + y + '" r="4" fill="' + col + '"/>';
    svg += '<text x="' + x + '" y="' + (y - 10) + '" fill="' + C.muted + '" font-size="11" text-anchor="middle">' + rnd(r.accuracy) + '%</text>';
    const label = (r.answerer_model || "?").replace("gpt-5-mini", "mini").replace("gpt-5", "g5");
    svg += '<text x="' + x + '" y="' + (h - padB + 18) + '" fill="' + C.faint + '" font-size="10.5" text-anchor="middle">' + esc(label) + '</text>';
    svg += '<text x="' + x + '" y="' + (h - padB + 32) + '" fill="' + C.faint + '" font-size="9.5" text-anchor="middle">' + esc((r.run_id || "").slice(-8)) + '</text>';
  });
  svg += '<text x="' + (padL - 30) + '" y="' + (padT + plotH / 2) + '" fill="' + C.faint + '" font-size="11" transform="rotate(-90 ' + (padL - 30) + ' ' + (padT + plotH / 2) + ')" text-anchor="middle">accuracy (%)</text>';
  svg += '</svg>';
  return svg;
}

function abilityBars(abilities, seriesA, seriesB) {
  const rowH = 30, padL = 4, padR = 8, padT = 8, labelW = 190, barArea = 540, valW = 44;
  const h = padT * 2 + abilities.length * rowH;
  const w = labelW + barArea + valW;
  const xAt = (v) => labelW + (barArea * v) / 100;
  let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" role="img">';
  abilities.forEach((ab, i) => {
    const cy = padT + i * rowH;
    svg += '<text x="' + padL + '" y="' + (cy + rowH / 2 + 4) + '" fill="' + C.muted + '" font-size="11.5">' + esc(ab) + '</text>';
    const bh = 9;
    const a = seriesA.data[i], b = seriesB ? seriesB.data[i] : null;
    if (a != null) {
      svg += '<rect x="' + labelW + '" y="' + (cy + 4) + '" width="' + (xAt(a) - labelW) + '" height="' + bh + '" fill="' + C.info + '" rx="2"/>';
      svg += '<text x="' + (xAt(a) + 5) + '" y="' + (cy + 4 + bh) + '" fill="' + C.faint + '" font-size="10">' + rnd(a) + '</text>';
    }
    if (b != null) {
      svg += '<rect x="' + labelW + '" y="' + (cy + 4 + bh + 2) + '" width="' + (xAt(b) - labelW) + '" height="' + bh + '" fill="' + C.success + '" rx="2"/>';
      svg += '<text x="' + (xAt(b) + 5) + '" y="' + (cy + 4 + bh + 2 + bh) + '" fill="' + C.faint + '" font-size="10">' + rnd(b) + '</text>';
    }
  });
  svg += '</svg>';
  return svg;
}

const AMB_ORDER = { ok: 0, low_n: 1, missing: 2 };
function ambSorted(records) {
  return records.slice().sort((a, b) =>
    ((AMB_ORDER[a.status] ?? 3) - (AMB_ORDER[b.status] ?? 3)) || ((b.accuracy || 0) - (a.accuracy || 0)));
}

function ambValueText(r) {
  if (r.status === "missing") return "pending";
  if (r.spread != null) return fix1(r.accuracy) + "% spread " + fix1(r.spread) + "pp ×" + r.repeats;
  let t = fix1(r.accuracy) + "%";
  if (r.ci != null) t += " ±" + fix1(r.ci);
  if (r.status === "low_n") t += " (n=" + r.n + ", low)";
  return t;
}

// Horizontal accuracy bars with a 95% CI whisker per dataset. Datasets with no
// canonical run (or too few samples) render as a faint dashed track so coverage
// gaps read as information rather than absence.
function benchmarkBars(records) {
  const recs = ambSorted(records);
  const rowH = 34, padT = 10, padB = 18, labelW = 140, barArea = 430, valW = 170;
  const w = labelW + barArea + valW;
  const plotBottom = padT + recs.length * rowH;
  const h = plotBottom + padB;
  const xAt = (v) => labelW + (barArea * Math.max(0, Math.min(100, v))) / 100;
  let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" role="img">';
  for (let t = 0; t <= 100; t += 25) {
    const x = xAt(t);
    svg += '<line x1="' + x + '" y1="' + padT + '" x2="' + x + '" y2="' + plotBottom + '" stroke="' + C.stroke + '" stroke-width="1"/>';
    svg += '<text x="' + x + '" y="' + (plotBottom + 13) + '" fill="' + C.faint + '" font-size="9.5" text-anchor="middle">' + t + '</text>';
  }
  recs.forEach((r, i) => {
    const cy = padT + i * rowH, midY = cy + rowH / 2, bh = 10, barY = midY - bh / 2;
    svg += '<text x="0" y="' + (midY + 4) + '" fill="' + C.muted + '" font-size="11.5">' + esc(r.label) + '</text>';
    if (r.status === "ok" || r.status === "low_n") {
      const acc = r.accuracy || 0;
      const col = r.status === "ok" ? C.info : C.warn;
      svg += '<rect x="' + labelW + '" y="' + barY + '" width="' + (xAt(acc) - labelW) + '" height="' + bh + '" fill="' + col + '" rx="2"/>';
      if (r.ci != null && r.ci > 0) {
        const lo = xAt(acc - r.ci), hi = xAt(acc + r.ci), wy = midY;
        svg += '<line x1="' + lo + '" y1="' + wy + '" x2="' + hi + '" y2="' + wy + '" stroke="' + C.text + '" stroke-width="1.5"/>';
        svg += '<line x1="' + lo + '" y1="' + (wy - 4) + '" x2="' + lo + '" y2="' + (wy + 4) + '" stroke="' + C.text + '" stroke-width="1.5"/>';
        svg += '<line x1="' + hi + '" y1="' + (wy - 4) + '" x2="' + hi + '" y2="' + (wy + 4) + '" stroke="' + C.text + '" stroke-width="1.5"/>';
      }
    } else {
      svg += '<rect x="' + labelW + '" y="' + barY + '" width="' + barArea + '" height="' + bh + '" fill="none" stroke="' + C.faint + '" stroke-width="1" stroke-dasharray="4 4" rx="2"/>';
    }
    const vcol = r.status === "missing" ? C.faint : C.muted;
    svg += '<text x="' + (labelW + barArea + 8) + '" y="' + (midY + 4) + '" fill="' + vcol + '" font-size="10.5">' + esc(ambValueText(r)) + '</text>';
  });
  svg += '</svg>';
  return svg;
}

function ambTable(records) {
  let rows = "";
  ambSorted(records).forEach(r => {
    let acc;
    if (r.status === "missing") acc = '<span style="color:' + C.faint + '">pending</span>';
    else if (r.spread != null) acc = fix1(r.accuracy) + '% <span style="color:' + C.muted + '">(spread ' + fix1(r.spread) + 'pp, ×' + r.repeats + ')</span>';
    else if (r.ci != null) acc = fix1(r.accuracy) + '% ± ' + fix1(r.ci) + (r.status === "low_n" ? ' <span style="color:' + C.warn + '">low n</span>' : '');
    else acc = fix1(r.accuracy) + '%';
    const ret = r.avg_retrieve_time_ms != null ? Math.round(r.avg_retrieve_time_ms) + ' ms' : '—';
    const tok = r.avg_context_tokens != null ? Math.round(r.avg_context_tokens) : '—';
    const n = r.n ? r.n : '—';
    rows += '<tr><td>' + esc(r.label) + '</td><td class="num">' + acc + '</td><td class="num">' + ret + '</td><td class="num">' + tok + '</td><td class="num">' + n + '</td></tr>';
  });
  return '<table><thead><tr><th>Benchmark</th><th class="num">Accuracy (95% CI)</th><th class="num">Recall latency (median)</th><th class="num">Context tokens (median)</th><th class="num">n</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function bestByAnswerer(beam, key) {
  const runs = beam.filter(r => (r.answerer_model || "").indexOf(key) >= 0);
  if (!runs.length) return null;
  return runs.reduce((best, r) => (r.accuracy > best.accuracy ? r : best));
}

function el(html) { const d = document.createElement("div"); d.innerHTML = html; return d.firstElementChild; }

function render() {
  const app = document.getElementById("app");
  const scores = data.scores || [];
  const beam = scores.filter(r => r.benchmark === "beam-judged");
  const amb = scores.filter(r => r.benchmark === "amb");
  const sc = data.status_counts || {};
  const best = beam.length ? rnd(Math.max(...beam.map(r => r.accuracy))) : null;
  const loco = amb.find(r => r.dataset === "locomo" && r.status === "ok");

  let html = "";
  html += '<h1>AutoMem eval scoreboard</h1>';
  html += '<p class="sub">Internal experiment tracker view. Generated ' + esc(data.generated_at || "") + ' by <code>scripts/experiment_index.py</code>. Not for publication.</p>';

  const total = (data.threads || []).length;
  html += '<div class="stats">';
  html += '<div class="stat"><div class="v">' + total + '</div><div class="l">Threads tracked</div></div>';
  html += '<div class="stat"><div class="v" style="color:' + C.success + '">' + (sc.adopted || 0) + '</div><div class="l">Adopted</div></div>';
  html += '<div class="stat"><div class="v" style="color:' + C.warn + '">' + (sc["in-progress"] || 0) + '</div><div class="l">In progress</div></div>';
  html += '<div class="stat"><div class="v" style="color:' + C.info + '">' + (best != null ? best + "%" : "n/a") + '</div><div class="l">Best BEAM judged</div></div>';
  if (loco) html += '<div class="stat"><div class="v" style="color:' + C.success + '">' + fix1(loco.accuracy) + '%</div><div class="l">LoCoMo (AMB)</div></div>';
  html += '</div>';

  if (!beam.length && !amb.length) {
    html += '<div class="note" style="margin-top:20px">No benchmark score artifacts were reachable from the scanned data root. Regenerate with <code>--data-root</code> pointing at the checkout that holds <code>data/results/beam-judged/</code>, and <code>--amb-outputs</code> at the AMB harness outputs.</div>';
    app.innerHTML = html;
    return;
  }

  if (beam.length) {
  const full = beam.filter(r => (r.total_questions || 0) >= 100).sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  const traj = full.length ? full : beam.slice().sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  html += '<h2>BEAM judged accuracy across runs</h2>';
  html += '<div class="panel">' + lineChart(traj, 75) + '</div>';
  html += '<div class="legend"><span><i style="background:' + C.info + '"></i>gpt-5 answerer</span><span><i style="background:' + C.success + '"></i>gpt-5-mini answerer</span><span><i style="background:' + C.warn + '"></i>Hindsight 100K = 75%</span></div>';
  html += '<p class="caption">Y: overall accuracy (%). X: chronological runs with ' + (full.length ? "&ge;100" : "all") + ' questions. Source: data/results/beam-judged. The answerer-model swap (g5 &rarr; mini) is the main driver across the 75% line.</p>';

  const g5 = bestByAnswerer(beam, "gpt-5") && !bestByAnswerer(beam, "mini") ? bestByAnswerer(beam, "gpt-5") : beam.filter(r => (r.answerer_model || "") === "gpt-5").reduce((b, r) => (!b || r.accuracy > b.accuracy ? r : b), null);
  const mini = bestByAnswerer(beam, "mini");
  const abilities = data.abilities || [];
  const present = (run) => run && run.by_ability && abilities.some(a => run.by_ability[a] != null);
  if (present(g5) || present(mini)) {
    const seriesA = { name: g5 ? "gpt-5 (" + (g5.run_id || "").slice(-8) + " · " + g5.accuracy + "%)" : "gpt-5", data: abilities.map(a => g5 && g5.by_ability ? g5.by_ability[a] : null) };
    const seriesB = mini ? { name: "gpt-5-mini (" + (mini.run_id || "").slice(-8) + " · " + mini.accuracy + "%)", data: abilities.map(a => mini.by_ability ? mini.by_ability[a] : null) } : null;
    html += '<h2>Per-ability accuracy</h2>';
    html += '<div class="panel">' + abilityBars(abilities, seriesA, seriesB) + '</div>';
    html += '<div class="legend"><span><i style="background:' + C.info + '"></i>' + esc(seriesA.name) + '</span>' + (seriesB ? '<span><i style="background:' + C.success + '"></i>' + esc(seriesB.name) + '</span>' : "") + '</div>';
    html += '<p class="caption">X: accuracy (%) per BEAM ability bucket. Best run per answerer model. Source: data/results/beam-judged.</p>';
  }

  html += '<h2>Run provenance</h2>';
  let rows = "";
  beam.slice().sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).forEach(r => {
    rows += '<tr><td><code>' + esc((r.run_id || "").slice(-8)) + '</code></td><td>' + esc((r.created_at || "").slice(0, 16).replace("T", " ")) + '</td><td>' + esc(r.tier || "") + '</td><td>' + esc(r.answerer_model || "") + '</td><td class="num">' + esc(r.total_questions || "") + '</td><td class="num">' + esc(rnd(r.accuracy)) + '%</td></tr>';
  });
  html += '<table><thead><tr><th>Run</th><th>When</th><th>Tier</th><th>Answerer</th><th class="num">Q</th><th class="num">Accuracy</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  if (amb.length) {
    html += '<h2>Cross-benchmark accuracy (AMB · Gemini answerer)</h2>';
    html += '<div class="panel">' + benchmarkBars(amb) + '</div>';
    html += '<div class="legend"><span><i style="background:' + C.info + '"></i>full run</span><span><i style="background:' + C.warn + '"></i>low n (&lt;30)</span><span><i style="background:' + C.faint + '"></i>pending</span><span>whisker = 95% CI</span></div>';
    html += ambTable(amb);
    html += '<p class="caption">Accuracy (bar) with 95% CI whisker per AMB dataset; the table adds the cost axes (recall latency, context tokens). Source: agent-memory-benchmark/outputs &mdash; neutral Gemini-3.1-Pro answerer + judge. Numbers are in parity with <code>runners/amb_aggregate.py</code>. Internal only.</p>';
  }

  html += '<h2>Experiment threads</h2>';
  let trows = "";
  (data.threads || []).forEach(t => {
    trows += '<tr><td><code>' + esc(t.id) + '</code></td><td><span class="tag ' + esc(t.status) + '">' + esc(t.status) + '</span></td><td>' + esc(t.decision || "") + '</td><td class="num">' + esc(t.artifact_count || 0) + '</td><td>' + esc(t.updated || "") + '</td></tr>';
  });
  html += '<table><thead><tr><th>Thread</th><th>Status</th><th>Decision</th><th class="num">Artifacts</th><th>Updated</th></tr></thead><tbody>' + trows + '</tbody></table>';

  app.innerHTML = html;
}
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
