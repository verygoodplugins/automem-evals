import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from supersede_gap import adapter as sg


def item(qid, flags, qtype="knowledge-update", answer="Denver"):
    """Two dated sessions; ``flags`` = (earlier, later) index of the has_answer user turn or None."""
    sessions = []
    for n, flag in enumerate(flags):
        sessions.append([
            {"role": "user" if t % 2 == 0 else "assistant", "content": f"{qid} s{n} t{t}", "has_answer": t == flag}
            for t in range(3)
        ])
    return {
        "question_id": qid, "question_type": qtype, "question": f"Where do I live? ({qid})", "answer": answer,
        "question_date": "2023/06/01 (Thu) 00:58", "haystack_session_ids": [f"{qid}_1", f"{qid}_2"],
        "haystack_dates": ["2023/05/25 (Thu) 20:21", "2023/05/27 (Sat) 10:20"], "haystack_sessions": sessions,
    }


SYNTHETIC = [
    item("aaa111", (0, 2)),
    item("bbb222", (0, 0)),
    item("ccc333", (None, 1), answer=120),
    item("ddd444_abs", (None, None)),
    item("eee555", (0, 0), qtype="temporal-reasoning"),
]
SYNTH_EXPECTED = {"questions": 4, "strata": {"both_labeled": 2, "late_only": 1, "abstention": 1}}


class WithDataset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = self.write(SYNTHETIC)
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.tasks = sg.load_tasks(self.path, expected_sha256=self.digest, expected=SYNTH_EXPECTED)

    def write(self, data, name="oracle.json"):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(data))
        return path

    def task(self, qid):
        return next(t for t in self.tasks if t.question_id == qid)


class LoaderTests(WithDataset):
    def test_pins_are_well_formed(self):
        self.assertRegex(sg.DATASET_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(sg.UPSTREAM_COMMIT, r"^[0-9a-f]{40}$")
        self.assertRegex(sg.DATASET_REVISION, r"^[0-9a-f]{40}$")
        self.assertEqual(sg.UPSTREAM_LICENSE, "Apache-2.0")

    def test_filters_question_type_and_classifies_strata(self):
        self.assertEqual([t.question_id for t in self.tasks], ["aaa111", "bbb222", "ccc333", "ddd444_abs"])
        self.assertEqual([t.stratum for t in self.tasks], ["both_labeled", "both_labeled", "late_only", "abstention"])
        self.assertEqual([t.scorable for t in self.tasks], [True, True, True, False])

    def test_gold_is_cast_to_str(self):
        self.assertEqual(self.task("ccc333").gold, "120")

    def test_wrong_hash_fails_closed(self):
        with self.assertRaises(sg.PinError):
            sg.load_tasks(self.path, expected_sha256="0" * 64, expected=SYNTH_EXPECTED)

    def test_shape_drift_fails_closed(self):
        drifted = dict(SYNTH_EXPECTED, questions=5)
        with self.assertRaises(sg.PinError):
            sg.load_tasks(self.path, expected_sha256=self.digest, expected=drifted)

    def test_rejects_unchronological_or_extra_sessions(self):
        swapped = item("fff666", (0, 0))
        swapped["haystack_dates"].reverse()
        three = item("ggg777", (0, 0))
        three["haystack_session_ids"].append("x")
        three["haystack_dates"].append("2023/05/28 (Sun) 10:00")
        three["haystack_sessions"].append(three["haystack_sessions"][0])
        for bad in (swapped, three):
            path = self.write([bad], name="bad.json")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(sg.PinError):
                sg.load_tasks(path, expected_sha256=digest, expected={})

    @unittest.skipUnless(os.environ.get("SUPERSEDE_ORACLE_JSON"), "set SUPERSEDE_ORACLE_JSON to the pinned file")
    def test_pinned_file_matches_expected_shape(self):
        tasks = sg.load_tasks(Path(os.environ["SUPERSEDE_ORACLE_JSON"]))
        self.assertEqual(len(tasks), 78)
        self.assertEqual(sum(len(sg.build_plan(t, "x", "supersede_oracle")["links"]) for t in tasks), 72)


class PlanTests(WithDataset):
    def test_tags_are_isolated_valid_and_lowercase(self):
        tags = [sg.question_tag("run1", t.question_id) for t in self.tasks]
        self.assertEqual(len(set(tags)), len(tags))
        self.assertEqual(sg.question_tag("run1", "AbC123"), "supersede:run1:abc123")
        for bad in ("Run 1", "", "a:b"):
            with self.assertRaises(ValueError):
                sg.question_tag(bad, "aaa111")

    def test_writes_never_carry_the_evidence_label(self):
        for variant in sg.VARIANTS:
            plan = sg.build_plan(self.task("aaa111"), "r", variant)
            self.assertNotIn("has_answer", json.dumps(plan))
            self.assertEqual(len(plan["writes"]), 6)
            for write in plan["writes"]:
                self.assertEqual(set(write["metadata"]), {"question_id", "session_id", "turn_index", "role"})
                self.assertEqual(write["tags"], [plan["tag"]])

    def test_timestamps_strictly_increase_in_write_order(self):
        stamps = [w["timestamp"] for w in sg.build_plan(self.task("aaa111"), "r", "plain")["writes"]]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(len(set(stamps)), len(stamps))
        self.assertTrue(stamps[0].startswith("2023-05-25T20:21:00Z"))

    def test_plain_has_no_links(self):
        self.assertTrue(all(sg.build_plan(t, "r", "plain")["links"] == [] for t in self.tasks))

    def test_oracle_links_earlier_evidence_to_later_evidence(self):
        plan = sg.build_plan(self.task("aaa111"), "r", "supersede_oracle")
        by_key = {w["key"]: w for w in plan["writes"]}
        (link,) = plan["links"]
        self.assertEqual((link["old"], link["new"]), ("aaa111:s0:t0", "aaa111:s1:t2"))
        self.assertEqual(link["relation"], "INVALIDATED_BY")
        self.assertEqual(link["at"], by_key[link["new"]]["timestamp"])
        self.assertLess(by_key[link["old"]]["timestamp"], link["at"])

    def test_oracle_skips_unlabeled_sides_and_abstention(self):
        self.assertEqual(sg.build_plan(self.task("ccc333"), "r", "supersede_oracle")["links"], [])
        self.assertEqual(sg.build_plan(self.task("ddd444_abs"), "r", "supersede_oracle")["links"], [])
        self.assertEqual(sg.evidence_keys(self.task("ccc333")), (set(), {"ccc333:s1:t1"}))
        self.assertEqual(sg.evidence_keys(self.task("ddd444_abs")), (set(), set()))

    def test_read_params_are_identical_across_variants(self):
        for t in self.tasks:
            probes = [sg.build_plan(t, "r", v)["probe"] for v in sg.VARIANTS]
            self.assertEqual(probes[0], probes[1])
        probe = probes[0]
        self.assertEqual((probe["tag_match"], probe["current_only"], probe["end"]), ("exact", True, "2023-06-01T00:58:00Z"))

    def test_unknown_variant_is_rejected(self):
        with self.assertRaises(ValueError):
            sg.build_plan(self.tasks[0], "r", "supersede_detected")


class ScoringTests(WithDataset):
    def test_classify_text(self):
        self.assertEqual(sg.classify_text("You live in Denver.", "Denver", ["Boston"])["class"], "current")
        self.assertEqual(sg.classify_text("You live in Boston.", "Denver", ["Boston"])["class"], "stale")
        both = sg.classify_text("Boston, then Denver", "Denver", ["Boston"])
        self.assertEqual((both["class"], both["detail"]), ("other", "both"))
        none = sg.classify_text("No idea", "Denver", ["Boston"])
        self.assertEqual((none["class"], none["detail"]), ("other", "neither"))
        self.assertEqual(sg.classify_text("about 250 miles", "25", [])["class"], "other")  # word boundary

    def test_classify_text_without_stale_values_cannot_report_stale(self):
        self.assertEqual(sg.classify_text("You live in Boston.", "Denver", [])["class"], "other")

    def test_classify_recall_reports_ranks(self):
        stale, current = {"a"}, {"b"}
        self.assertEqual(sg.classify_recall(["x", "b"], stale, current),
                         {"class": "current", "detail": None, "current_rank": 2, "stale_rank": None})
        self.assertEqual(sg.classify_recall(["a", "x"], stale, current)["class"], "stale")
        leaked = sg.classify_recall(["a", "b"], stale, current)
        self.assertEqual((leaked["class"], leaked["detail"]), ("other", "both"))
        self.assertEqual(sg.classify_recall(["x"], stale, current)["detail"], "neither")

    def verdicts(self, classes):
        return {qid: {"class": c, "detail": "neither" if c == "other" else None} for qid, c in classes.items()}

    def test_aggregate_is_not_scored_when_any_verdict_is_missing(self):
        out = sg.aggregate(self.tasks, self.verdicts({"aaa111": "current", "bbb222": "stale"}))
        self.assertEqual(out["status"], "not_scored")
        self.assertIsNone(out["rates"])
        self.assertIn("1 of 3", out["reason"])
        self.assertEqual(sg.aggregate(self.tasks, None)["status"], "not_scored")

    def test_aggregate_without_scorable_questions_is_not_scored(self):
        out = sg.aggregate([self.task("ddd444_abs")], {})
        self.assertEqual((out["status"], out["reason"], out["rates"]), ("not_scored", "no scorable questions", None))

    def test_aggregate_rejects_unknown_verdict_classes(self):
        with self.assertRaises(ValueError):
            sg.aggregate(self.tasks, self.verdicts({"aaa111": "current", "bbb222": "stale", "ccc333": "correct"}))

    def test_aggregate_rates_sum_to_one_and_exclude_abstention(self):
        out = sg.aggregate(self.tasks, self.verdicts({"aaa111": "current", "bbb222": "stale", "ccc333": "other"}))
        self.assertEqual((out["status"], out["n"]), ("scored", 3))
        self.assertAlmostEqual(sum(out["rates"].values()), 1.0)
        self.assertEqual(out["other_breakdown"], {"neither": 1})
        self.assertEqual(out["by_stratum"]["late_only"]["n"], 1)
        self.assertNotIn("abstention", out["by_stratum"])


class ReportTests(WithDataset):
    def test_report_is_not_scored_with_cold_and_matured_slots(self):
        report = sg.build_report(self.tasks, "r")
        self.assertEqual((report["status"], report["paper_comparable"], report["maturation"]), ("not_scored", False, "cold"))
        for name, variant in report["variants"].items():
            self.assertIsNone(variant["cold"]["rates"], name)
            self.assertEqual(variant["matured"]["status"], "not_run")
            self.assertIn("maturation", variant["matured"]["reason"])
        self.assertTrue(report["variants"]["supersede_oracle"]["uses_oracle_labels"])
        self.assertFalse(report["variants"]["plain"]["uses_oracle_labels"])
        self.assertEqual(report["variants"]["supersede_oracle"]["plan"]["links"], 2)
        self.assertEqual(report["dataset"]["scorable"], 3)
        self.assertIn("never AutoMem scores", report["paper_baselines"]["label"])

    def test_report_only_scores_when_every_variant_is_fully_verdicted(self):
        full = {t.question_id: {"class": "current", "detail": None} for t in self.tasks if t.scorable}
        partial = sg.build_report(self.tasks, "r", verdicts={"plain": full})
        self.assertEqual(partial["status"], "not_scored")
        scored = sg.build_report(self.tasks, "r", verdicts={"plain": full, "supersede_oracle": full})
        self.assertEqual(scored["status"], "scored")
        self.assertFalse(scored["paper_comparable"])

    def test_cli_writes_report_and_plan_and_refuses_unpinned_data(self):
        out, plan = Path(self.tmp.name) / "report.json", Path(self.tmp.name) / "plan.jsonl"
        argv = ["--data", str(self.path), "--run-id", "smoke", "--out", str(out), "--plan-out", str(plan), "--limit", "2"]
        with self.assertRaises(SystemExit) as refused:  # synthetic file is not the pinned hash
            sg.main(argv)
        self.assertIn("refusing", str(refused.exception))
        with self.assertRaises(SystemExit):  # argparse rejects a non-positive limit
            sg.main(argv[:-1] + ["0"])
        original = (sg.DATASET_SHA256, sg.EXPECTED)
        sg.DATASET_SHA256, sg.EXPECTED = self.digest, SYNTH_EXPECTED
        self.addCleanup(lambda: setattr(sg, "DATASET_SHA256", original[0]) or setattr(sg, "EXPECTED", original[1]))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sg.main(argv), 0)
        report = json.loads(out.read_text())
        self.assertEqual((report["status"], report["subset"]), ("not_scored", "first-2"))
        lines = [json.loads(line) for line in plan.read_text().splitlines()]
        self.assertEqual(len(lines), 4)  # 2 questions x 2 variants
        self.assertTrue(all(re.match(r"^supersede:smoke:", p["tag"]) for p in lines))


if __name__ == "__main__":
    unittest.main()
