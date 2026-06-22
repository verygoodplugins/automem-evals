import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_script(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ExperimentIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("experiment_index")

    def test_orphan_detection_ignores_registered_artifact_globs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_json(
                root / "docs" / "experiments" / "registry.json",
                [
                    {
                        "id": "EXP-REGISTERED",
                        "title": "Registered",
                        "status": "adopted",
                        "hypothesis": "Registered artifacts should not be orphaned.",
                        "result": "Registered result.",
                        "decision": "Adopted.",
                        "started": "2026-01-01",
                        "updated": "2026-01-02",
                        "artifacts": ["data/results/registered/**"],
                        "related": [],
                    }
                ],
            )
            self.write_text(root / "data" / "results" / "registered" / "report.md", "# Registered\n")
            self.write_text(root / "data" / "results" / "orphan" / "report.md", "# Orphan\n")

            index = self.mod.build_index(root, worktrees=[], prs=[])

            orphan_paths = {artifact["path"] for artifact in index["orphan_artifacts"]}
            self.assertNotIn("data/results/registered/report.md", orphan_paths)
            self.assertIn("data/results/orphan/report.md", orphan_paths)

    def test_status_rollup_counts_registry_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_json(
                root / "docs" / "experiments" / "registry.json",
                [
                    self.thread("EXP-A", "adopted"),
                    self.thread("EXP-B", "in-progress"),
                    self.thread("EXP-C", "in-progress"),
                ],
            )

            index = self.mod.build_index(root, worktrees=[], prs=[])

            self.assertEqual(index["status_counts"], {"adopted": 1, "in-progress": 2})

    def test_worktree_classification_uses_pr_state(self):
        worktrees = [
            {
                "path": "/repo",
                "branch": "feat/merged",
                "head": "abc1234",
                "dirty_entries": 0,
            },
            {
                "path": "/repo-2",
                "branch": "feat/no-pr",
                "head": "def5678",
                "dirty_entries": 3,
            },
        ]
        prs = [
            {
                "number": 19,
                "headRefName": "feat/merged",
                "state": "MERGED",
                "title": "Merged feature",
            }
        ]

        classified = self.mod.classify_worktrees(worktrees, prs)

        by_branch = {item["branch"]: item for item in classified}
        self.assertEqual(by_branch["feat/merged"]["status"], "merged")
        self.assertTrue(by_branch["feat/merged"]["cleanup_candidate"])
        self.assertEqual(by_branch["feat/no-pr"]["status"], "in-flight")
        self.assertFalse(by_branch["feat/no-pr"]["cleanup_candidate"])

    def test_git_worktree_parser_preserves_nested_branch_names(self):
        porcelain = (
            "worktree /repo\n"
            "HEAD abc123456789\n"
            "branch refs/heads/feat/beam-judged-harness\n"
            "\n"
        )

        worktrees = self.mod.parse_git_worktree_porcelain(porcelain)

        self.assertEqual(worktrees[0]["branch"], "feat/beam-judged-harness")

    def test_markdown_and_manifest_artifacts_are_summarized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_json(root / "docs" / "experiments" / "registry.json", [])
            self.write_text(
                root / "data" / "results" / "20260417-230940-comparison.md",
                "# Ruleset comparison - 2026-04-17T23:09:40\n",
            )
            self.write_json(
                root / "data" / "results" / "beam-judged" / "run-100K" / "MANIFEST.json",
                {
                    "schema": "automem-evals.beam-judged-manifest.v1",
                    "run_id": "run",
                    "created_at": "2026-06-15T22:42:20+00:00",
                    "metadata": {"tier": "100K", "total_questions": 400},
                },
            )

            artifacts = self.mod.discover_artifacts(root)

            by_path = {artifact["path"]: artifact for artifact in artifacts}
            self.assertEqual(
                by_path["data/results/20260417-230940-comparison.md"]["kind"],
                "ruleset-comparison",
            )
            self.assertEqual(
                by_path["data/results/beam-judged/run-100K/MANIFEST.json"]["schema"],
                "automem-evals.beam-judged-manifest.v1",
            )

    def test_status_render_handles_threads_without_worktrees(self):
        index = {
            "generated_at": "2026-06-22T18:00:00+00:00",
            "threads": [
                {
                    "id": "EXP-NO-WORKTREE",
                    "title": "No worktree",
                    "status": "adopted",
                    "hypothesis": "No worktree should be fine.",
                    "decision": "Adopted.",
                    "updated": "2026-06-22",
                    "related": [],
                    "artifact_count": 0,
                    "worktree_status": None,
                }
            ],
            "worktrees": [],
            "orphan_artifacts": [],
        }

        rendered = self.mod.render_status(index)

        self.assertIn("EXP-NO-WORKTREE", rendered)

    def test_extract_scores_reads_beam_judged_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_json(
                root / "data" / "results" / "beam-judged" / "20260616-042452-1d46f08a-100K" / "results.json",
                {
                    "schema": "automem-evals.beam-judged-results.v1",
                    "run_id": "20260616-042452-1d46f08a",
                    "created_at": "2026-06-16T05:34:15.319399+00:00",
                    "metadata": {
                        "tier": "100K",
                        "answerer_model": "gpt-5",
                        "judge_model": "gpt-5",
                        "total_questions": 400,
                    },
                    "metrics_by_cutoff": {
                        "top_100": {
                            "overall": {"total": 400, "correct": 281, "accuracy": 70.25, "avg_score": 0.649},
                            "by_question_type": {
                                "abstention": {"total": 40, "correct": 21, "accuracy": 52.5},
                                "summarization": {"total": 40, "correct": 25, "accuracy": 62.5},
                            },
                        }
                    },
                },
            )

            scores = self.mod.extract_scores(root)

            self.assertEqual(len(scores), 1)
            record = scores[0]
            self.assertEqual(record["benchmark"], "beam-judged")
            self.assertEqual(record["run_id"], "20260616-042452-1d46f08a")
            self.assertEqual(record["tier"], "100K")
            self.assertEqual(record["answerer_model"], "gpt-5")
            self.assertEqual(record["accuracy"], 70.25)
            self.assertEqual(record["by_ability"]["summarization"], 62.5)

    def test_build_index_uses_data_root_for_scores(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_data:
            root = Path(tmp_root)
            data_root = Path(tmp_data)
            self.write_json(root / "docs" / "experiments" / "registry.json", [])
            self.write_json(
                data_root / "data" / "results" / "beam-judged" / "run-100K" / "results.json",
                {
                    "run_id": "run",
                    "created_at": "2026-06-16T00:00:00+00:00",
                    "metadata": {"tier": "100K", "answerer_model": "gpt-5-mini"},
                    "metrics_by_cutoff": {
                        "top_100": {"overall": {"accuracy": 82.25}, "by_question_type": {}}
                    },
                },
            )

            index = self.mod.build_index(root, data_root=data_root, worktrees=[], prs=[])

            self.assertEqual(len(index["scores"]), 1)
            self.assertEqual(index["scores"][0]["accuracy"], 82.25)

    def test_scoreboard_html_is_self_contained_and_embeds_data(self):
        index = {
            "generated_at": "2026-06-22T18:00:00+00:00",
            "threads": [
                {"id": "EXP-BEAM-JUDGED", "title": "Native judged BEAM", "status": "in-progress",
                 "decision": "Park.", "updated": "2026-06-22", "related": [], "artifact_count": 1},
            ],
            "status_counts": {"in-progress": 1},
            "scores": [
                {
                    "benchmark": "beam-judged",
                    "run_id": "20260616-042452-1d46f08a",
                    "created_at": "2026-06-16T05:34:15+00:00",
                    "tier": "100K",
                    "answerer_model": "gpt-5",
                    "accuracy": 70.25,
                    "by_ability": {"abstention": 52.5},
                }
            ],
            "orphan_artifacts": [],
            "worktrees": [],
        }

        html = self.mod.render_scoreboard_html(index)

        self.assertIn("<svg", html)
        self.assertIn("20260616-042452-1d46f08a", html)
        self.assertIn("70.25", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_extract_scores_reads_amb_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_amb:
            root = Path(tmp_root)
            amb = Path(tmp_amb)
            # 40 questions, 30 correct -> 75.0% accuracy, n=40, finite CI.
            self.write_json(
                amb / "locomo" / "automem-sub" / "rag" / "locomo10.json",
                {
                    "dataset": "locomo",
                    "split": "locomo10",
                    "accuracy": 0.75,
                    "avg_retrieve_time_ms": 132.0,
                    "avg_context_tokens": 4768.0,
                    "answer_llm": "gemini:gemini-3.1-pro-preview",
                    "results": [{"correct": i < 30} for i in range(40)],
                },
            )

            scores = self.mod.extract_scores(root, amb_outputs=amb)

            amb_scores = [s for s in scores if s["benchmark"] == "amb"]
            by_dataset = {(s["dataset"], s["split"]): s for s in amb_scores}
            loco = by_dataset[("locomo", "locomo10")]
            self.assertEqual(loco["status"], "ok")
            self.assertEqual(loco["accuracy"], 75.0)
            self.assertEqual(loco["n"], 40)
            self.assertIsNotNone(loco["ci"])
            self.assertGreater(loco["ci"], 0)
            self.assertEqual(loco["avg_retrieve_time_ms"], 132.0)
            # Datasets without a canonical run are emitted as pending, not dropped.
            self.assertEqual(by_dataset[("longmemeval", "s")]["status"], "missing")
            self.assertIn(("beam", "100k"), by_dataset)  # repro entry present

    def test_extract_scores_skips_amb_when_outputs_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.mod.extract_scores(root), [])
            self.assertEqual(self.mod.extract_scores(root, amb_outputs=root / "missing"), [])

    def test_amb_repro_is_partial_until_all_runs_present(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_amb:
            root = Path(tmp_root)
            amb = Path(tmp_amb)

            def write_beam(run, acc, n):
                self.write_json(
                    amb / "beam" / run / "rag" / "100k.json",
                    {
                        "accuracy": acc,
                        "avg_retrieve_time_ms": 200.0,
                        "avg_context_tokens": 3000.0,
                        "results": [{"correct": True} for _ in range(n)],
                    },
                )

            # 2 of the 3 declared repro runs present -> partial, not ok.
            write_beam("automem-sub-rep1", 0.70, 100)
            write_beam("automem-sub-rep2", 0.74, 100)
            beam = self._amb_beam(self.mod.extract_scores(root, amb_outputs=amb))
            self.assertEqual(beam["status"], "partial")
            self.assertEqual(beam["repeats"], 2)
            self.assertEqual(beam["expected_repeats"], 3)
            self.assertIsNotNone(beam["accuracy"])

            # All three present -> ok.
            write_beam("automem-sub-rep3", 0.72, 100)
            beam = self._amb_beam(self.mod.extract_scores(root, amb_outputs=amb))
            self.assertEqual(beam["status"], "ok")
            self.assertEqual(beam["repeats"], 3)

    def test_build_index_respects_registry_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_json(root / "docs" / "experiments" / "registry.json", [])
            self.write_json(root / "custom" / "reg.json", [self.thread("EXP-CUSTOM", "adopted")])

            index = self.mod.build_index(
                root, registry_path=Path("custom/reg.json"), worktrees=[], prs=[]
            )

            self.assertEqual({t["id"] for t in index["threads"]}, {"EXP-CUSTOM"})
            self.assertEqual(index["status_counts"], {"adopted": 1})

    def _amb_beam(self, scores):
        return next(
            s for s in scores
            if s["benchmark"] == "amb" and s["dataset"] == "beam" and s["split"] == "100k"
        )

    def test_scoreboard_renders_amb_section(self):
        index = {
            "generated_at": "2026-06-22T18:00:00+00:00",
            "threads": [],
            "status_counts": {},
            "scores": [
                {
                    "benchmark": "amb",
                    "dataset": "locomo",
                    "split": "locomo10",
                    "label": "LoCoMo",
                    "run_name": "automem-sub",
                    "accuracy": 85.1,
                    "ci": 1.8,
                    "spread": None,
                    "n": 1540,
                    "avg_retrieve_time_ms": 132.0,
                    "avg_context_tokens": 4768.0,
                    "answer_llm": "gemini:gemini-3.1-pro-preview",
                    "status": "ok",
                    "repeats": 1,
                }
            ],
            "orphan_artifacts": [],
            "worktrees": [],
        }

        html = self.mod.render_scoreboard_html(index)

        self.assertIn("Cross-benchmark accuracy", html)
        self.assertIn("LoCoMo", html)
        self.assertIn("<svg", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def write_json(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def write_text(self, path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def thread(self, thread_id: str, status: str):
        return {
            "id": thread_id,
            "title": thread_id,
            "status": status,
            "hypothesis": "Hypothesis.",
            "result": "Result.",
            "decision": "Decision.",
            "started": "2026-01-01",
            "updated": "2026-01-01",
            "artifacts": [],
            "related": [],
        }


if __name__ == "__main__":
    unittest.main()
