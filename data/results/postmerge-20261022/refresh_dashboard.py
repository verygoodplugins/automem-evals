"""Refresh this campaign's views with an artifact overlay and bounded history.

Run from the repository root with --data-root pointing at the raw-results checkout.
To reuse a captured index without scanning artifacts/VCS, import this module and
call write_with_provenance(index, status_path, index_path, scoreboard_path).
The three retained AMB values are historical snapshot records, never fresh runs.
Requires Python 3.11+ like the existing dashboard generator.
"""
import copy
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


def retain_historical_scores(index, snapshot):
    """Copy the index, filling only exact, freshly missing AMB placeholders.

    No rows are added; valid current zero scores, failures and unmatched runs are
    left intact. A retained row copies every original score/model field unchanged.
    """
    retained = copy.deepcopy(index)
    source = snapshot.get("source", {})
    required = ("ref", "commit", "commit_date", "index_path", "index_generated_at", "index_sha256")
    if (any(not isinstance(source.get(field), str) or not source[field] for field in required)
            or source["commit"] != SOURCE_COMMIT or source["index_sha256"] != SOURCE_INDEX_SHA256
            or source["index_path"] != "docs/experiments/index.json"):
        return retained
    historical = {_score_key(row): row for row in snapshot.get("scores", []) if _complete_historical(row)}
    for position, row in enumerate(retained.get("scores", [])):
        old = historical.get(_score_key(row))
        if (old is None or row.get("status") != "missing" or row.get("accuracy") is not None
                or type(row.get("n")) is not int or row["n"] != 0):
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


def write_with_provenance(index, status_path, index_path, scoreboard_path=None):
    """Write captured index/views directly; never rediscover artifacts or VCS."""
    retained = retain_historical_scores(index, load_snapshot())
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
    # Importing this one-off wrapper must not alter the normal generator.
    previous_discover, previous_write = dashboard.discover_artifacts, dashboard.write_outputs
    dashboard.discover_artifacts, dashboard.write_outputs = discover_with_overlay, write_with_provenance
    try:
        return dashboard.main()
    finally:
        dashboard.discover_artifacts, dashboard.write_outputs = previous_discover, previous_write


if __name__ == "__main__":
    raise SystemExit(main())
