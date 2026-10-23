"""Offline retention tests; no artifact scan, VCS scan or provider requests."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("postmerge_refresh_dashboard", HERE / "refresh_dashboard.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class HistoricalScoreRetentionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((HERE / "historical-scores.json").read_text())
        self.index = {"generated_at": "2026-10-22T12:00:00+00:00", "threads": [],
                      "worktrees": [], "orphan_artifacts": [], "status_counts": {},
                      "scores": [self.missing(row) for row in self.snapshot["scores"]]}

    @staticmethod
    def missing(row):
        result = copy.deepcopy(row)
        result.update(status="missing", accuracy=None, n=0, answer_llm=None)
        return result

    def test_fills_matching_missing_rows_with_exact_values_models_and_provenance(self):
        retained = refresh.retain_historical_scores(self.index, self.snapshot)
        self.assertEqual(len(retained["scores"]), 3)
        for actual, historical in zip(retained["scores"], self.snapshot["scores"]):
            provenance = actual.pop("score_provenance")
            self.assertEqual(actual, historical)
            self.assertEqual(provenance["kind"], "historical_snapshot_retained")
            self.assertEqual(provenance["source_commit"], self.snapshot["source"]["commit"])
            self.assertEqual(provenance["source_generated_at"], "2026-06-22T20:26:29+00:00")
            self.assertEqual(provenance["source_index_sha256"], self.snapshot["source"]["index_sha256"])
            self.assertEqual(provenance["source_path"], "docs/experiments/index.json")

    def test_current_accuracy_zero_and_explicit_failure_are_preserved(self):
        for change in ({"status": "ok", "accuracy": 0, "n": 20},
                       {"status": "missing", "accuracy": 0, "n": 0},
                       {"status": "failed", "accuracy": None, "n": 0},
                       {"status": "partial", "accuracy": None, "n": 0},
                       {"status": "missing", "accuracy": None, "n": 1}):
            with self.subTest(change=change):
                index = copy.deepcopy(self.index)
                index["scores"][0].update(change)
                self.assertEqual(refresh.retain_historical_scores(index, self.snapshot)["scores"][0], index["scores"][0])

    def test_unmatched_keys_and_new_rows_are_not_replaced_or_added(self):
        for field in ("benchmark", "dataset", "split", "run_name"):
            with self.subTest(field=field):
                index = {"scores": [dict(self.index["scores"][0], **{field: "new-value"})]}
                self.assertEqual(refresh.retain_historical_scores(index, self.snapshot), index)
        self.assertEqual(refresh.retain_historical_scores({"scores": []}, self.snapshot), {"scores": []})
        restored = refresh.retain_historical_scores({"scores": []}, self.snapshot, restore_absent=True)
        self.assertEqual({refresh._score_key(row) for row in restored["scores"]}, refresh.RETAINABLE_KEYS)

    def test_invalid_or_incomplete_historical_rows_are_ignored(self):
        for change in ({"status": "partial"}, {"status": "missing"}, {"n": 0}, {"n": True},
                       {"accuracy": None}, {"accuracy": True}, {"accuracy": float("nan")},
                       {"accuracy": float("inf")}, {"repeats": 2, "expected_repeats": 3}):
            with self.subTest(change=change):
                historical = dict(self.snapshot["scores"][-1], **change)
                snapshot = dict(self.snapshot, scores=[historical])
                index = {"scores": [copy.deepcopy(self.index["scores"][-1])]}
                self.assertEqual(refresh.retain_historical_scores(index, snapshot), index)

    def test_retention_is_bounded_to_original_three_keys(self):
        historical = dict(self.snapshot["scores"][0], dataset="new-dataset")
        snapshot = dict(self.snapshot, scores=[historical])
        index = {"scores": [self.missing(historical)]}
        self.assertEqual(refresh.retain_historical_scores(index, snapshot), index)

    def test_unrecognized_source_commit_or_hash_is_ignored(self):
        for field in ("commit", "index_sha256"):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["source"][field] = "unrecognized-source"
                self.assertEqual(refresh.retain_historical_scores(self.index, snapshot), self.index)

    def test_inputs_are_not_mutated_and_retention_is_idempotent(self):
        before_index, before_snapshot = copy.deepcopy(self.index), copy.deepcopy(self.snapshot)
        retained = refresh.retain_historical_scores(self.index, self.snapshot)
        self.assertEqual(self.index, before_index)
        self.assertEqual(self.snapshot, before_snapshot)
        self.assertEqual(refresh.retain_historical_scores(retained, self.snapshot), retained)

    def test_status_and_html_show_historical_note_near_header(self):
        retained = refresh.retain_historical_scores(self.index, self.snapshot)
        status = refresh.render_status(retained)
        html = refresh.render_scoreboard_html(retained)
        for text in (status, html):
            for phrase in ("Historical AMB snapshot", "LoCoMo", "PersonaMem", "BEAM-100K",
                           "2026-06-22", "35fa73d", "archives are unavailable", "not fresh AMB"):
                self.assertIn(phrase, text)
        self.assertLess(status.index("Historical AMB snapshot"), status.index("## Thread Overview"))
        self.assertLess(html.index("<h1>AutoMem eval scoreboard</h1>"), html.index("Historical AMB snapshot"))
        self.assertLess(html.index("Historical AMB snapshot"), html.index("  const total ="))

    def test_no_retention_means_no_historical_note(self):
        index = dict(self.index, scores=[])
        self.assertNotIn("Historical AMB snapshot", refresh.render_status(index))
        self.assertNotIn("Historical AMB snapshot", refresh.render_scoreboard_html(index))

    def test_status_refresh_hint_uses_wrapper_with_or_without_retained_scores(self):
        for index in (dict(self.index, scores=[]), refresh.retain_historical_scores(self.index, self.snapshot)):
            with self.subTest(retained=bool(index["scores"])):
                rendered = refresh.render_status(index)
                self.assertIn("Refresh with `python3 data/results/postmerge-20261022/refresh_dashboard.py`.", rendered)
                self.assertNotIn("`python3 scripts/experiment_index.py`", rendered)

    def test_real_cli_missing_archives_restores_three_but_no_amb_restores_none(self):
        hooks = {name: getattr(refresh.dashboard, name) for name in ("parse_args", "discover_artifacts", "write_outputs")}
        for no_amb in (False, True):
            with self.subTest(no_amb=no_amb), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                argv = ["refresh_dashboard.py", "--root", str(root), "--data-root", str(root),
                        "--amb-outputs", "unavailable-archives", "--no-vcs"]
                if no_amb:
                    argv.append("--no-amb")
                with patch.object(sys, "argv", argv), patch.object(refresh, "original_discover", return_value=[]), \
                     patch.object(refresh.dashboard, "run_command", side_effect=AssertionError("must not scan VCS")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(refresh.main(), 0)
                self.assertFalse((root / "unavailable-archives").exists())
                captured = json.loads((root / "docs/experiments/index.json").read_text())
                rows = [row for row in captured["scores"] if row.get("benchmark") == "amb"]
                self.assertEqual(len(rows), 0 if no_amb else 3)
                if not no_amb:
                    self.assertEqual({refresh._score_key(row) for row in rows}, refresh.RETAINABLE_KEYS)
                    self.assertTrue(all(row["score_provenance"]["source_generated_at"] == "2026-06-22T20:26:29+00:00" for row in rows))
                for name in ("STATUS.md", "scoreboard.html"):
                    text = (root / "docs/experiments" / name).read_text()
                    self.assertEqual("Historical AMB snapshot" in text, not no_amb)
                for name, original in hooks.items():
                    self.assertIs(getattr(refresh.dashboard, name), original)

    def test_cli_restores_generator_hooks_after_failure(self):
        hooks = {name: getattr(refresh.dashboard, name) for name in ("parse_args", "discover_artifacts", "write_outputs")}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(sys, "argv", ["refresh_dashboard.py", "--root", tmp, "--no-vcs"]), \
             patch.object(refresh.dashboard, "main", side_effect=RuntimeError("test generator failure")):
            with self.assertRaisesRegex(RuntimeError, "test generator failure"):
                refresh.main()
        for name, original in hooks.items():
            self.assertIs(getattr(refresh.dashboard, name), original)

    def test_real_cli_restores_only_absent_canonical_sources(self):
        for historical in self.snapshot["scores"]:
            for present in (True, False):
                with self.subTest(dataset=historical["dataset"], present=present), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    outputs = root / "amb-outputs"
                    # For BEAM, one malformed repeat must block replacement of
                    # the aggregate even when the other repeat files are absent.
                    source = outputs / historical["dataset"] / historical["run_name"].split("+")[0] / "rag" / (historical["split"] + ".json")
                    source.parent.mkdir(parents=True)
                    if present:
                        source.write_text("{malformed current result")
                    argv = ["refresh_dashboard.py", "--root", str(root), "--data-root", str(root),
                            "--amb-outputs", "amb-outputs", "--no-vcs"]
                    with patch.object(sys, "argv", argv), patch.object(refresh, "original_discover", return_value=[]), \
                         patch.object(refresh.dashboard, "run_command", side_effect=AssertionError("must not scan VCS")), \
                         contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(refresh.main(), 0)
                    captured = json.loads((root / "docs/experiments/index.json").read_text())
                    row = next(row for row in captured["scores"] if refresh._score_key(row) == refresh._score_key(historical))
                    self.assertEqual(source.exists(), present)
                    if present:
                        self.assertEqual(row["status"], "missing")
                        self.assertIsNone(row["accuracy"])
                        self.assertEqual(row["n"], 0)
                        self.assertNotIn("score_provenance", row)
                    else:
                        self.assertEqual(row["accuracy"], historical["accuracy"])
                        self.assertEqual(row["score_provenance"]["kind"], "historical_snapshot_retained")
                    retained = [row for row in captured["scores"] if "score_provenance" in row]
                    self.assertEqual(len(retained), 2 if present else 3)

    def test_write_existing_captured_index_requires_no_scans(self):
        before = copy.deepcopy(self.index)
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("STATUS.md", "index.json", "scoreboard.html")]
            with patch.object(refresh.dashboard, "build_index", side_effect=AssertionError("must not rescan")), \
                 patch.object(refresh.dashboard, "discover_artifacts", side_effect=AssertionError("must not rescan")):
                refresh.write_with_provenance(self.index, *paths)
            saved = json.loads(paths[1].read_text())
            self.assertEqual(len([row for row in saved["scores"] if "score_provenance" in row]), 3)
            self.assertIn("Historical AMB snapshot", paths[0].read_text())
            self.assertIn("Historical AMB snapshot", paths[2].read_text())
            rendered_once = [path.read_bytes() for path in paths]
            with patch.object(refresh.dashboard, "build_index", side_effect=AssertionError("must not rescan")), \
                 patch.object(refresh.dashboard, "discover_artifacts", side_effect=AssertionError("must not rescan")):
                refresh.write_with_provenance(saved, *paths)
            self.assertEqual([path.read_bytes() for path in paths], rendered_once)
        self.assertEqual(self.index, before)


if __name__ == "__main__":
    unittest.main()
