"""Unit tests for sweep_corpus.py — pure-logic helpers only.

The HTTP and process-orchestration paths are exercised by the dry-run smoke
in data/sweep_runs/. These tests just guard the audit/safety helpers that
were added in response to the 2026-05-01 Codex adversarial review:
- write_full_backup must persist the complete record (not just id+prefix).
- assert_no_regression behaviour stays correct as preserve_regressions[]
  feeds the new fail-closed exit path.

Run: python3 -m unittest runners.test_sweep_corpus
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_corpus as sc


class WriteFullBackupTests(unittest.TestCase):
    def test_writes_jsonl_with_complete_records(self):
        memories = [
            {"id": "abc", "content": "x" * 200, "tags": ["build", "npm"], "metadata": {"k": "v"}, "created_at": "2026-04-01T00:00:00Z"},
            {"id": "def", "content": "y" * 50, "tags": ["test"], "type": "Insight"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            path = sc.write_full_backup(d, "filter-1", memories)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "filter-1.backup.jsonl")
            lines = path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            r0 = json.loads(lines[0])
            self.assertEqual(r0["id"], "abc")
            # Backup must include the full content (not the 80-char prefix from .ids.txt)
            self.assertEqual(len(r0["content"]), 200)
            self.assertEqual(r0["tags"], ["build", "npm"])
            self.assertEqual(r0["metadata"], {"k": "v"})

    def test_creates_report_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "nested" / "dir"
            self.assertFalse(d.exists())
            sc.write_full_backup(d, "f", [{"id": "x"}])
            self.assertTrue(d.exists())

    def test_empty_candidates_writes_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            path = sc.write_full_backup(d, "empty", [])
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(), "")


class AssertNoRegressionTests(unittest.TestCase):
    """Codex finding #1 hinges on this returning a list of problems that
    feeds the new fail-closed exit path. Make sure the contract is stable.
    """

    def test_no_regression_returns_empty(self):
        before = {"preserve A": 19, "preserve B": 5}
        after = {"preserve A": 19, "preserve B": 5}
        preserve = [{"name": "preserve A", "min_results": 10}, {"name": "preserve B", "min_results": 5}]
        self.assertEqual(sc.assert_no_regression(before, after, preserve), [])

    def test_count_dropped_flagged(self):
        before = {"preserve A": 19}
        after = {"preserve A": 18}
        preserve = [{"name": "preserve A", "min_results": 10}]
        problems = sc.assert_no_regression(before, after, preserve)
        self.assertEqual(len(problems), 1)
        self.assertIn("preserve A", problems[0])
        self.assertIn("dropped", problems[0])

    def test_min_results_floor_flagged(self):
        before = {"preserve A": 11}
        after = {"preserve A": 11}  # no drop, but below floor
        preserve = [{"name": "preserve A", "min_results": 15}]
        problems = sc.assert_no_regression(before, after, preserve)
        self.assertEqual(len(problems), 1)
        self.assertIn("min_results", problems[0])


if __name__ == "__main__":
    unittest.main()
