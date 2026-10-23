"""Refresh this campaign's views with an artifact overlay and bounded history.

Run from the repository root with --data-root pointing at the raw-results checkout.
To reuse a captured index without scanning artifacts/VCS, import this module and
call write_with_provenance(index, status_path, index_path, scoreboard_path).
The three retained AMB values are historical snapshot records, never fresh runs.
Requires Python 3.11+ like the existing dashboard generator.
"""
import copy
from functools import partial
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = Path(__file__).with_name("historical-scores.json")
SOURCE_COMMIT = "35fa73d78703b4af6387762df7b74884520dc29f"
SOURCE_INDEX_SHA256 = "91ab7b31c053df20fac695065b9119f222441b21d4268303d58e2c43185a40da"
KEY_FIELDS = ("benchmark", "dataset", "split", "run_name")
REFRESH_COMMAND = "python3 data/results/postmerge-20261022/refresh_dashboard.py"
RETAINABLE_KEYS = {
    ("amb", "locomo", "locomo10", "automem-sub"),
    ("amb", "personamem", "32k", "automem-sub"),
    ("amb", "beam", "100k", "automem-sub-rep1+automem-sub-rep2+automem-sub-rep3"),
}
sys.path.insert(0, str(ROOT))
from scripts import experiment_index as dashboard

original_discover = dashboard.discover_artifacts


def load_snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _score_key(row):
    if not isinstance(row, dict):
        return None
    key = tuple(row.get(field) for field in KEY_FIELDS)
    return key if all(isinstance(value, str) and value for value in key) else None


def _complete_historical(row):
    if _score_key(row) not in RETAINABLE_KEYS or row.get("status") != "ok":
        return False
    if type(row.get("n")) is not int or row["n"] <= 0:
        return False
    accuracy = row.get("accuracy")
    if type(accuracy) not in (int, float) or not math.isfinite(accuracy):
        return False
    if "repeats" in row and (type(row["repeats"]) is not int or row["repeats"] <= 0):
        return False
    if "expected_repeats" in row:
        expected = row["expected_repeats"]
        if type(expected) is not int or expected <= 0 or row.get("repeats") != expected:
            return False
    return True


def _amb_sources_absent(outputs, key):
    _, dataset, split, run_name = key
    for run in run_name.split("+"):
        path = outputs / dataset / run / "rag" / f"{split}.json"
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return False  # Inaccessible is not evidence of absence.
        return False  # Includes malformed files and dangling symlinks.
    return True


def retain_historical_scores(index, snapshot, *, restore_absent=False, amb_outputs=None):
    """Copy the index, filling only exact, freshly missing AMB placeholders.

    By default no rows are added; CLI-only restore_absent seeds just the three
    curated keys when raw archives are absent. Current scores/failures stay intact.
    CLI supplies amb_outputs to verify actual source absence; a loader's missing
    placeholder alone cannot distinguish absence from a malformed current file.
    A retained row copies every original score/model field unchanged.
    """
    retained = copy.deepcopy(index)
    source = snapshot.get("source", {})
    required = ("ref", "commit", "commit_date", "index_path", "index_generated_at", "index_sha256")
    if (any(not isinstance(source.get(field), str) or not source[field] for field in required)
            or source["commit"] != SOURCE_COMMIT or source["index_sha256"] != SOURCE_INDEX_SHA256
            or source["index_path"] != "docs/experiments/index.json"):
        return retained
    historical = {_score_key(row): row for row in snapshot.get("scores", []) if _complete_historical(row)}
    if restore_absent:
        rows = retained.setdefault("scores", [])
        existing = {_score_key(row) for row in rows}
        for key in historical:
            if key not in existing:
                rows.append(dict(zip(KEY_FIELDS, key), status="missing", accuracy=None, n=0))
    for position, row in enumerate(retained.get("scores", [])):
        old = historical.get(_score_key(row))
        if (old is None or row.get("status") != "missing" or row.get("accuracy") is not None
                or type(row.get("n")) is not int or row["n"] != 0):
            continue
        if amb_outputs is not None and not _amb_sources_absent(amb_outputs, _score_key(row)):
            continue
        replacement = copy.deepcopy(old)
        replacement["score_provenance"] = {
            "kind": "historical_snapshot_retained",
            "reason": "Raw archives unavailable; retained historical value, not a fresh AMB result.",
            "source_ref": source["ref"],
            "source_commit": source["commit"],
            "source_commit_date": source["commit_date"],
            "source_generated_at": source["index_generated_at"],
            "source_path": source["index_path"],
            "source_index_sha256": source["index_sha256"],
        }
        retained["scores"][position] = replacement
    return retained


def _historical_note(index):
    rows = [row for row in index.get("scores", [])
            if row.get("score_provenance", {}).get("kind") == "historical_snapshot_retained"]
    if not rows:
        return ""
    labels = ", ".join(row.get("label") or row["dataset"] for row in rows)
    provenance = rows[0]["score_provenance"]
    return (f"Historical AMB snapshot: {labels} values retained from the index generated "
            f"{provenance['source_generated_at']} because the raw archives are unavailable. "
            "These are historical values, not fresh AMB results. "
            f"Source: {provenance['source_ref']}@{provenance['source_commit'][:7]}, "
            f"{provenance['source_path']}; full source commit/hash recorded per retained row in index.json.")


def render_status(index):
    rendered = dashboard.render_status(index)
    generated_hint = "This file is generated by `python3 scripts/experiment_index.py`."
    if rendered.count(generated_hint) != 1:
        raise ValueError("Status refresh hint changed; wrapper entrypoint needs review")
    rendered = rendered.replace(generated_hint, f"Refresh with `{REFRESH_COMMAND}`.", 1)
    note = _historical_note(index)
    if not note:
        return rendered
    heading, separator, rest = rendered.partition("\n\n")
    return heading + separator + note + "\n\n" + rest


def render_scoreboard_html(index):
    # Stable embedded key order survives save/reload, keeping repeated writes
    # byte-identical as well as preserving the historical header annotation.
    ordered = json.loads(json.dumps(index, sort_keys=True, allow_nan=False))
    rendered = dashboard.render_scoreboard_html(ordered)
    note = _historical_note(index)
    if not note:
        return rendered
    heading = "  html += '<h1>AutoMem eval scoreboard</h1>';"
    if rendered.count(heading) != 1:
        raise ValueError("Scoreboard header changed; historical note needs review")
    visible_note = '<p class="note">' + html.escape(note) + '</p>'
    return rendered.replace(heading, heading + "\n  html += " + json.dumps(visible_note) + ";", 1)


def discover_with_overlay(data_root):
    artifacts = {artifact["path"]: artifact for artifact in original_discover(data_root)}
    artifacts.update({artifact["path"]: artifact for artifact in original_discover(ROOT)})
    return list(artifacts.values())


def write_with_provenance(index, status_path, index_path, scoreboard_path=None, *, restore_absent=False, amb_outputs=None):
    """Write captured index/views directly; never rediscover artifacts or VCS."""
    retained = retain_historical_scores(index, load_snapshot(), restore_absent=restore_absent, amb_outputs=amb_outputs)
    retained["artifact_overlay_root"] = str(ROOT)
    outputs = [(status_path, render_status(retained)),
               (index_path, json.dumps(retained, indent=2, sort_keys=True, allow_nan=False) + "\n")]
    if scoreboard_path is not None:
        outputs.append((scoreboard_path, render_scoreboard_html(retained)))
    for path, content in outputs:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main():
    args = dashboard.parse_args()
    root = args.root.resolve()
    data_root = args.data_root.resolve() if args.data_root else root
    amb_outputs = None if args.no_amb else args.amb_outputs
    if amb_outputs is not None and not amb_outputs.is_absolute():
        amb_outputs = (data_root / amb_outputs).resolve()
    restore_absent = amb_outputs is not None and not amb_outputs.exists()
    # Reuse parsed arguments so the generator and restoration share one decision.
    # All hooks are restored even when the underlying generator raises.
    previous_discover, previous_write, previous_parse = (
        dashboard.discover_artifacts, dashboard.write_outputs, dashboard.parse_args)
    dashboard.discover_artifacts = discover_with_overlay
    dashboard.write_outputs = partial(write_with_provenance, restore_absent=restore_absent, amb_outputs=amb_outputs)
    dashboard.parse_args = lambda: args
    try:
        return dashboard.main()
    finally:
        dashboard.discover_artifacts, dashboard.write_outputs, dashboard.parse_args = (
            previous_discover, previous_write, previous_parse)


if __name__ == "__main__":
    raise SystemExit(main())
