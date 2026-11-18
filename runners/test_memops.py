"""Unit tests for the offline MemOps scaffold (no network, no AutoMem, no model)."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from memops import adapter as m

MEMOPS_DIR = os.environ.get("MEMOPS_DIR")  # optional pinned checkout for the real-data test


def plan(arm, setting="adjacent_operation", record=None):
    record = record or m.fixture()
    return m.ingest_plan(record, setting=setting, arm=arm, run_tag="t", record_id="fx",
                         injected=m.fixture_injected(record))


def kinds(p, name):
    return [s for s in p["steps"] if s["step"] == name]


def result(planned, recalled):
    """A recall result carrying the planned question's composite identity."""
    return {"record_id": planned["record_id"], "setting": planned["setting"],
            "question_pair_id": planned["question_pair_id"], "recalled": recalled}


class ValidationTests(unittest.TestCase):
    def test_fixture_is_valid_and_defects_fail_closed(self):
        self.assertTrue(m.validate_record(m.fixture()))
        bad = m.fixture()
        bad["operations"][0]["trigger_span"]["turn_index"] = 99
        with self.assertRaisesRegex(ValueError, "outside"):
            m.validate_record(bad)
        bad = m.fixture()
        bad["operations"][0]["trigger_span"]["turn_index"] = 2  # an assistant turn
        with self.assertRaisesRegex(ValueError, "not a user turn"):
            m.validate_record(bad)
        bad = m.fixture()
        bad["answer"][0]["evaluation_type"] = "Nope"
        with self.assertRaisesRegex(ValueError, "unknown probe"):
            m.validate_record(bad)

    def test_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / m.UPSTREAM["evidence_dir"]
            target.mkdir(parents=True)
            (target / "A01_update.json").write_text("{}")
            with self.assertRaises(m.PinMismatch):
                m.verify_pin(tmp)

    def test_clock_is_deterministic_and_monotonic(self):
        self.assertEqual(m.narrative_ts(1, 1), "2026-01-01T00:01:00Z")
        self.assertLess(m.narrative_ts(1, 59), m.narrative_ts(2, 1))
        self.assertNotIn("datetime.now", Path(m.__file__).read_text())

    def test_no_network_imports(self):
        source = Path(m.__file__).read_text()
        for name in ("urllib", "socket", "http.client", "requests", "subprocess"):
            self.assertNotIn(f"import {name}", source)


class WriteArmTests(unittest.TestCase):
    def test_raw_turns_is_a_pure_store_control(self):
        p = plan("raw_turns")
        self.assertEqual({s["step"] for s in p["steps"]}, {"store"})
        self.assertEqual(len(p["steps"]), 5)  # every user turn

    def test_soft_arm_supersedes_and_forgets_without_a_tombstone(self):
        p = plan("oracle_lifecycle_soft")
        assoc = kinds(p, "associate")
        invalidated = [a for a in assoc if a["type"] == "INVALIDATED_BY"]
        self.assertEqual([(a["from"], a["to"]) for a in invalidated], [("c1t1", "c2t1")])
        patched = {s["ref"] for s in kinds(p, "patch")}
        self.assertEqual(patched, {"c1t1", "c1t3"})  # superseded city, forgotten dog
        stored = {s["ref"] for s in kinds(p, "store")}
        self.assertNotIn("c2t3", stored)  # the forget trigger turn is never stored
        self.assertFalse(kinds(p, "delete"))

    def test_tentative_value_never_replaces_the_confirmed_one(self):
        p = plan("oracle_lifecycle_soft")
        tentative = next(s for s in kinds(p, "store") if s["ref"] == "c2t5")
        self.assertEqual(tentative["body"]["confidence"], m.TENTATIVE_CONFIDENCE)
        self.assertIn("memops:validity:tentative", tentative["body"]["tags"])
        self.assertNotIn("c2t5", {s["ref"] for s in kinds(p, "patch")})
        self.assertNotIn("c2t5", {a["to"] for a in kinds(p, "associate")
                                  if a["type"] == "INVALIDATED_BY"})

    def test_hard_arm_deletes_the_forgotten_target_only(self):
        p = plan("oracle_lifecycle_hard")
        self.assertEqual([s["ref"] for s in kinds(p, "delete")], ["c1t3"])
        self.assertEqual({s["ref"] for s in kinds(p, "patch")}, {"c1t1"})

    def test_inplace_arm_rewrites_content_and_loses_history(self):
        p = plan("oracle_inplace")
        edit = next(s for s in kinds(p, "patch") if "content" in s["body"])
        self.assertEqual(edit["ref"], "c1t1")
        self.assertIn("Porto", edit["body"]["content"])
        self.assertFalse([a for a in kinds(p, "associate") if a["type"] == "INVALIDATED_BY"])

    def test_reflection_is_an_insight_derived_from_its_evidence(self):
        p = plan("oracle_lifecycle_soft")
        reflection = next(s for s in kinds(p, "store") if s["ref"] == "op6r")
        self.assertEqual(reflection["body"]["type"], "Insight")
        derived = {(a["from"], a["to"]) for a in kinds(p, "associate") if a["type"] == "DERIVED_FROM"}
        self.assertEqual(derived, {("op6r", "c1t1"), ("op6r", "c2t1")})

    def test_tentative_reflection_keeps_its_uncertainty(self):
        record = m.fixture()
        record["operations"][5]["validity"] = "tentative"
        for arm in m.ARMS[1:]:
            reflection = next(s for s in kinds(plan(arm, record=record), "store") if s["ref"] == "op6r")
            self.assertEqual(reflection["body"]["confidence"], m.TENTATIVE_CONFIDENCE, arm)
            self.assertIn("memops:validity:tentative", reflection["body"]["tags"], arm)
        confirmed = next(s for s in kinds(plan("oracle_lifecycle_soft"), "store") if s["ref"] == "op6r")
        self.assertEqual(confirmed["body"]["confidence"], 0.9)
        self.assertIn("memops:validity:confirmed", confirmed["body"]["tags"])

    @staticmethod
    def after_reflection(kind, validity="confirmed"):
        """Fixture plus a later op on the reflection's own target ('habit')."""
        record = m.fixture()
        record["operations"][5]["validity"] = validity
        trigger = {"segment_index": 2, "turn_index": 3, "quote": ""}
        record["operations"].append({
            "operation_id": "op7", "type": kind, "validity": "confirmed", "trigger_span": trigger,
            "target": {"target_id": "habit", "target_name": "habit"}, "old_value": None,
            "new_value": None if kind == "forget" else "Settles down", "evidence_spans": [trigger]})
        return record

    def test_forget_reaches_a_reflection_of_the_same_target(self):
        record = self.after_reflection("forget")
        soft = plan("oracle_lifecycle_soft", record=record)
        self.assertEqual(soft["warnings"], [])
        self.assertEqual([s["body"] for s in kinds(soft, "patch") if s["ref"] == "op6r"],
                         [{"t_invalid": m.narrative_ts(2, 3)}])
        hard = plan("oracle_lifecycle_hard", record=record)
        self.assertIn("op6r", [s["ref"] for s in kinds(hard, "delete")])

    def test_update_supersedes_a_confirmed_reflection_but_not_a_tentative_one(self):
        confirmed = plan("oracle_lifecycle_soft", record=self.after_reflection("update"))
        self.assertIn(("op6r", "c2t3"), {(a["from"], a["to"]) for a in kinds(confirmed, "associate")
                                         if a["type"] == "INVALIDATED_BY"})
        self.assertTrue([s for s in kinds(confirmed, "patch") if s["ref"] == "op6r"])
        tentative = plan("oracle_lifecycle_soft", record=self.after_reflection("update", "tentative"))
        self.assertFalse([a for a in kinds(tentative, "associate") if a["type"] == "INVALIDATED_BY"
                          and a["from"] == "op6r"])
        self.assertIn("op7: update without a predecessor", tentative["warnings"])
        # still bound to its target, so a forget reaches it even though it was never current
        forgotten = self.after_reflection("forget", "tentative")
        self.assertTrue([s for s in kinds(plan("oracle_lifecycle_soft", record=forgotten), "patch")
                         if s["ref"] == "op6r"])

    def test_inplace_update_is_not_stored_again_when_a_reflection_cites_it(self):
        p = plan("oracle_inplace")
        stored = [s["ref"] for s in kinds(p, "store")]
        self.assertNotIn("c2t1", stored)  # the update trigger lives in the patched c1t1
        self.assertEqual(len(stored), len(set(stored)))
        derived = {a["to"] for a in kinds(p, "associate") if a["type"] == "DERIVED_FROM"}
        self.assertEqual(derived, {"c1t1"})  # the reflection links the patched memory itself

    def test_retracted_operation_is_skipped_not_applied(self):
        record = m.fixture()
        record["operations"][4]["validity"] = "retracted"
        p = plan("oracle_lifecycle_soft", record=record)
        self.assertEqual([s["reason"] for s in kinds(p, "skip")], ["retracted"])
        self.assertNotIn("c2t5", {s["ref"] for s in kinds(p, "store")})

    def test_longitudinal_adds_filler_in_every_arm_and_keeps_the_trace(self):
        for arm in m.ARMS:
            p = plan(arm, "longitudinal_operation")
            filler = [s for s in kinds(p, "store") if s["role"] == "filler"]
            self.assertEqual(len(filler), 6, arm)
        soft = plan("oracle_lifecycle_soft", "longitudinal_operation")
        old = next(s for s in kinds(soft, "store") if s["ref"] == "c1t1")
        new = next(s for s in kinds(soft, "store") if s["ref"] == "c2t1")
        self.assertLess(old["body"]["timestamp"], new["body"]["timestamp"])

    def test_evidence_not_at_its_offset_fails_closed(self):
        record = m.fixture()
        injected = m.fixture_injected(record)
        injected["injection_metadata"]["insertions"][0]["insertion_index"] = 0
        with self.assertRaisesRegex(ValueError, "insertion offset"):
            m.locate_evidence(record, injected)


class ProbeReportTests(unittest.TestCase):
    def setUp(self):
        self.plans = m.recall_plan(m.fixture(), setting="adjacent_operation", run_tag="t", record_id="fx")

    def test_recall_requests_are_scoped_and_carry_no_gold(self):
        wire = json.dumps([p["params"] for p in self.plans])
        for gold in ("must_include", "expected_answer", "Porto", "Biscuit"):
            self.assertNotIn(gold, wire)
        for p in self.plans:
            self.assertEqual((p["params"]["tag_match"], p["params"]["tag_mode"]), ("exact", "all"))
            self.assertEqual(p["params"]["state_mode"], m.STATE_MODE[p["probe"]])

    def test_unlabeled_questions_are_unknown_not_zero(self):
        verdict = m.classify_recall({"must_include": ["Porto"], "must_not_include": [],
                                     "stale_value": None}, ["I moved to PORTO"])
        self.assertEqual(verdict, {"support": True, "leak": None})
        leak = m.classify_recall({"must_include": [], "must_not_include": ["Biscuit"],
                                  "stale_value": None}, ["my dog biscuit"])
        self.assertEqual(leak, {"support": None, "leak": True})

    def test_aggregate_refuses_incomplete_coverage(self):
        with self.assertRaises(m.CoverageError):
            m.aggregate(self.plans, [result(self.plans[0], [])])

    def test_aggregate_does_not_let_one_record_cover_another(self):
        # question_pair_id repeats across records and settings at the pin, so a result for
        # record B must not satisfy record A's identical id.
        other = m.recall_plan(m.fixture(), setting="adjacent_operation", run_tag="t", record_id="other")
        self.assertEqual([p["question_pair_id"] for p in other],
                         [p["question_pair_id"] for p in self.plans])
        with self.assertRaises(m.CoverageError):
            m.aggregate(self.plans + other, [result(p, ["Porto"]) for p in other])

    def test_aggregate_does_not_let_one_setting_cover_another(self):
        long_plans = m.recall_plan(m.fixture(), setting="longitudinal_operation", run_tag="t", record_id="fx")
        with self.assertRaises(m.CoverageError):
            m.aggregate(self.plans + long_plans, [result(p, ["Porto"]) for p in long_plans])

    def test_aggregate_rejects_duplicate_and_unidentified_results(self):
        results = [result(p, []) for p in self.plans]
        with self.assertRaisesRegex(ValueError, "duplicate result"):
            m.aggregate(self.plans, results + [results[0]])
        with self.assertRaisesRegex(ValueError, "missing record_id"):
            m.aggregate(self.plans, [{"question_pair_id": p["question_pair_id"], "setting": p["setting"],
                                      "recalled": []} for p in self.plans])

    def test_aggregate_keeps_settings_in_separate_cells(self):
        long_plans = m.recall_plan(m.fixture(), setting="longitudinal_operation", run_tag="t", record_id="fx")
        results = ([result(p, ["I moved to Porto"]) for p in self.plans]
                   + [result(p, ["Lisbon only"]) for p in long_plans])
        cells = {(c["probe"], c["setting"]): c for c in m.aggregate(self.plans + long_plans, results)}
        self.assertEqual(cells[("StateTransition", "adjacent_operation")]["support_rate"], 1.0)
        self.assertEqual(cells[("StateTransition", "longitudinal_operation")]["support_rate"], 0.0)

    def test_aggregate_reports_per_probe_cells_without_answer_accuracy(self):
        results = [result(p, ["I moved to Porto", "I used to live in Lisbon"]) for p in self.plans]
        cells = {c["probe"]: c for c in m.aggregate(self.plans, results)}
        self.assertEqual(cells["StateTransition"]["support_rate"], 1.0)
        self.assertEqual(cells["StateTransition"]["leak_rate"], 1.0)  # stale Lisbon surfaced
        self.assertIsNone(cells["TargetBinding"]["leak_rate"])  # unlabeled
        self.assertEqual(cells["OperationApplication"]["leak_rate"], 0.0)
        for cell in cells.values():
            self.assertNotIn("accuracy", " ".join(cell))

    def test_report_is_not_scored_with_cold_and_matured_separate(self):
        report = m.build_report([])
        self.assertEqual((report["status"], report["paper_comparable"]), ("not_scored", False))
        self.assertIsNone(report["final_answer_accuracy"])
        self.assertEqual(set(report["variants"]), {"cold", "matured"})
        self.assertTrue(all(v["status"] == "not_scored" and not v["probe_cells"]
                            for v in report["variants"].values()))

    def test_cli_fixture_run_writes_only_a_not_scored_report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(m.main([]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "not_scored")
        self.assertEqual(len(report["plan_summaries"]), len(m.ARMS) * len(m.SETTINGS))
        self.assertEqual(copy.deepcopy(report["upstream"]["commit"]), m.UPSTREAM["commit"])


@unittest.skipUnless(MEMOPS_DIR, "set MEMOPS_DIR to a pinned MemOps checkout")
class PinnedDataTests(unittest.TestCase):
    def test_all_pinned_records_validate_and_locate(self):
        m.verify_pin(MEMOPS_DIR)
        root = Path(MEMOPS_DIR) / "generated_result"
        for path in sorted((root / "2-evidence_conversation").glob("*.json")):
            evidence = json.loads(path.read_text())
            injected = json.loads((root / "4-inject_evidence_with_distractors" / path.name).read_text())
            m.validate_record(evidence)
            m.locate_evidence(evidence, injected)


if __name__ == "__main__":
    unittest.main()
