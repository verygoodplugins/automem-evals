import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.benchmarks import meme_wiring_smoke as meme

STAMPS = ["2023/03/01 (Wed) 09:00", "2023/03/02 (Thu) 09:00", "2023/03/03 (Fri) 09:00",
          "2023/03/04 (Sat) 09:00", "2023/03/05 (Sun) 09:00"]


def question(task, slot, hop=None, key="gold_answer"):
    q = {"task_type": task, "entity": [slot], "entity_values": {slot: "v"}, "question": f"What is {slot}?", key: "v"}
    return {**q, "hop": hop} if hop else q


def episode(eid="pl_000", domain="personal_life"):
    return {
        "episode_id": eid, "domain": domain, "total_sessions": 5, "root": "health", "has_2hop": False,
        "tasks": [], "dependency_edges_used": [], "evidence_session_indices": [1, 3],
        "sessions": [{"session_id": f"{eid}-s{i}", "timestamp": t, "type": "evidence" if i % 2 else "filler",
                      "conversation": [{"role": "user", "content": f"turn {i}"}]} for i, t in enumerate(STAMPS)],
        "before_questions": {"timestamp": "2023/03/02 (Thu) 12:00", "position_after_session": 1, "questions": [
            question("ER", "name", key="expected_answer"), question("Cas", "med", 1, "expected_answer"),
            question("Abs", "appt", 1, "expected_answer"), question("Del", "hobby", key="expected_answer")]},
        "after_questions": {"timestamp": "2023/03/06 (Mon) 12:00", "position_after_session": 4, "questions": [
            question("ER", "name"), question("Agg", "pets"), question("Tr", "car"), question("Del", "hobby"),
            question("Cas", "med", 1), question("Abs", "appt", 1)]},
    }


EXPECTED = {
    "episodes": 2, "episodes_by_domain": {"personal_life": 1, "software_project": 1},
    "post_change_questions": 12, "post_change_by_domain": {"personal_life": 6, "software_project": 6},
    "post_change_by_task": dict.fromkeys(meme.TASKS, 2),
    "pre_change_by_task": {"ER": 2, "Cas": 2, "Abs": 2, "Del": 2},
    "hops": {"Cas": {"1": 2}, "Abs": {"1": 2}},
}


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "meme.json"

    def write(self, episodes):
        self.path.write_text(json.dumps(episodes), encoding="utf-8")
        return self.path

    def fixture(self):
        return [episode("pl_000", "personal_life"), episode("sw_000", "software_project")]

    def test_matching_fixture_passes_and_is_byte_deterministic(self):
        path = self.write(self.fixture())
        first, second = meme.smoke(path, pin=None, expected=EXPECTED), meme.smoke(path, pin=None, expected=EXPECTED)
        self.assertEqual(first["status"], "ok", first["errors"])
        self.assertEqual(meme.canonical(first), meme.canonical(second))
        self.assertEqual(first["schedule"], {"sessions_before_pre_change_questions": 4, "sessions_between_question_blocks": 6})

    def test_report_claims_no_calls_and_no_score(self):
        report = meme.smoke(self.write(self.fixture()), pin=None, expected=EXPECTED)
        self.assertEqual((report["model_calls"], report["network_calls"], report["automem_calls"]), (0, 0, 0))
        self.assertIsNone(report["automem_score"])
        self.assertNotIn("accuracy", json.dumps(report))

    def test_pinned_hash_mismatch_fails(self):
        report = meme.smoke(self.write(self.fixture()), expected=EXPECTED)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("sha256" in e for e in report["errors"]))

    def test_count_drift_is_reported(self):
        eps = self.fixture()
        eps[0]["after_questions"]["questions"].pop()
        report = meme.smoke(self.write(eps), pin=None, expected=EXPECTED)
        self.assertTrue(any(e.startswith("post_change_questions") for e in report["errors"]))

    def test_position_is_a_zero_based_inclusive_session_index(self):
        eps = self.fixture()
        eps[0]["before_questions"]["timestamp"] = "2023/03/03 (Fri) 12:00"  # after session index 2
        errors = meme.episode_errors(eps[0])
        self.assertEqual(len(errors), 1)
        self.assertIn("outside the window after session index 1", errors[0])

    def test_before_questions_must_precede_after_questions(self):
        ep = episode()
        ep["before_questions"]["position_after_session"] = 4
        ep["before_questions"]["timestamp"] = "2023/03/05 (Sun) 12:00"
        self.assertTrue(any("must precede" in e for e in meme.episode_errors(ep)))

    def test_trivial_pass_requires_a_matching_before_question(self):
        ep = episode()
        ep["before_questions"]["questions"] = [q for q in ep["before_questions"]["questions"] if q["task_type"] != "Del"]
        self.assertEqual(meme.episode_errors(ep), ["pl_000: Del hobby has no before-question (trivial-pass)"])

    def test_chronology_and_unique_session_ids_are_enforced(self):
        ep = episode()
        ep["sessions"][2]["session_id"] = ep["sessions"][1]["session_id"]
        ep["sessions"][3]["timestamp"] = STAMPS[0]
        errors = " ".join(meme.episode_errors(ep))
        self.assertIn("duplicate session ids", errors)
        self.assertIn("not chronological", errors)

    def test_adapter_view_drops_labels_and_schedule_never_leaks_future_sessions(self):
        ep = episode()
        for session in ep["sessions"]:
            self.assertEqual(set(meme.adapter_view(session)), set(meme.ADAPTER_SESSION_FIELDS))
            self.assertNotIn("type", meme.adapter_view(session))
        schedule = meme.ingest_schedule(ep)
        self.assertEqual(schedule["before"], ["pl_000-s0", "pl_000-s1"])
        self.assertEqual(schedule["between"], ["pl_000-s2", "pl_000-s3", "pl_000-s4"])

    def test_cli_writes_report_and_exits_nonzero_on_failure(self):
        out = Path(self.tmp.name) / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(meme.main(["--dataset", str(self.write(self.fixture())), "--output", str(out)]), 1)
        self.assertEqual(json.loads(out.read_text())["status"], "failed")  # fixture is not the pinned file


SUBSET_N = {"ER": 20, "Agg": 20, "Tr": 20, "Del": 20, "Cas": 30, "Abs": 25}  # 20 episodes
SUBSET_HOPS = {"Cas": (20, 10), "Abs": (20, 5)}


def task_row(task, correct, n=None, hop_n=None):
    n = n or meme.EXPECTED["post_change_by_task"][task]
    row = {"correct": correct, "n": n, "accuracy": round(correct / n, 6)}
    if task in meme.TRIVIAL_PASS_TASKS:
        row["pass_types"] = {"real_pass": correct, "trivial_pass": 1, "knew_but_failed": 0, "never_knew": n - correct - 1}
    if task in meme.HOP_TASKS:
        first, second = hop_n or (meme.EXPECTED["hops"][task]["1"], meme.EXPECTED["hops"][task]["2"])
        row["hops"] = {"1": {"correct": correct, "n": first}, "2": {"correct": 0, "n": second}}
    return row


def scored_result(subset=False):
    tasks = {task: task_row(task, (10 if subset else 50) if task in ("ER", "Agg", "Tr") else (2 if subset else 5),
                            SUBSET_N[task] if subset else None, SUBSET_HOPS.get(task) if subset else None)
             for task in meme.TASKS}
    mean = round(sum(row["accuracy"] for row in tasks.values()) / 6, 6)
    return {"run_status": "executed", "system": "automem-x", "paper_comparable": not subset,
            "dataset": {"episodes": 20 if subset else 100, "subset": subset, "hf_revision": meme.PIN["hf_revision"]},
            "answerer": {"model": "gpt-4.1-mini"}, "judge": {"model": "gpt-4o"}, "internal_llm": {"model": None},
            "embedding_model": "voyage-4", "arm": "M3a edges", "maturation": "cold",
            "automem": {"commit": "0123abc", "config": {"limit": 20, "current_only": False, "expansion": "client",
                                                       "enrichment": True}},
            "cost_usd": {"ingest_per_episode": 0.0, "inference_per_episode": 0.02, "judge_total": 1.5},
            "usage": {"tokens": 1_000_000, "calls": 4_000},
            "tasks": tasks, "overall": {"macro_mean": mean}}


class ContractTests(unittest.TestCase):
    def test_complete_executed_result_is_valid(self):
        self.assertEqual(meme.contract_errors(scored_result()), [])

    def test_wiring_only_result_must_not_carry_a_score(self):
        result = scored_result()
        self.assertTrue(meme.contract_errors({**result, "run_status": "wiring_only"}))
        result["run_status"] = "wiring_only"
        for row in result["tasks"].values():
            row["accuracy"] = None
        result["overall"]["macro_mean"] = None
        self.assertEqual(meme.contract_errors(result), [])

    def test_missing_disclosure_or_cost_is_rejected(self):
        for mutate, needle in ((lambda r: r["judge"].pop("model"), "judge.model"),
                               (lambda r: r["answerer"].update(model=""), "answerer.model"),
                               (lambda r: r["internal_llm"].clear(), "internal_llm.model"),
                               (lambda r: r["cost_usd"].pop("judge_total"), "judge_total")):
            result = copy.deepcopy(scored_result())
            mutate(result)
            self.assertTrue(any(needle in e for e in meme.contract_errors(result)), needle)

    def test_denominators_pass_types_and_macro_mean_are_checked(self):
        result = scored_result()
        result["tasks"]["Cas"]["n"] = 100
        result["tasks"]["Abs"]["pass_types"]["never_knew"] += 1
        errors = " ".join(meme.contract_errors(result))
        self.assertIn("tasks.Cas.n=100", errors)
        self.assertIn("tasks.Abs.pass_types", errors)
        self.assertNotIn("macro_mean", errors)  # no mean from a row whose own accuracy failed validation
        result = scored_result()
        result["overall"]["macro_mean"] = 0.9
        self.assertEqual(meme.contract_errors(result), ["overall.macro_mean must be the unweighted mean of the six task accuracies"])

    def test_paper_comparable_is_derived_from_answerer_judge_and_dataset(self):
        result = scored_result()
        result["judge"]["model"] = "gpt-5.4-mini-2026-03-17"
        self.assertTrue(any("paper_comparable must be False" in e for e in meme.contract_errors(result)))
        result["paper_comparable"] = False
        self.assertEqual(meme.contract_errors(result), [])

    def test_subset_run_must_be_declared(self):
        result = scored_result()
        result["dataset"]["episodes"] = 20
        result["paper_comparable"] = False
        self.assertTrue(any("subset" in e for e in meme.contract_errors(result)))

    def test_documented_disclosures_hops_and_usage_are_required(self):
        for mutate, needle in ((lambda r: r.pop("embedding_model"), "embedding_model"),
                               (lambda r: r.pop("arm"), "arm must"),
                               (lambda r: r.update(maturation="warm"), "maturation"),
                               (lambda r: r["automem"].pop("commit"), "automem.commit"),
                               (lambda r: r["automem"]["config"].pop("limit"), "automem.config.limit"),
                               (lambda r: r.pop("usage"), "usage.tokens"),
                               (lambda r: r["usage"].update(calls=-1), "usage.calls"),
                               (lambda r: r["dataset"].pop("hf_revision"), "dataset.hf_revision"),
                               (lambda r: r["dataset"].pop("subset"), "dataset.subset"),
                               (lambda r: r["tasks"]["Cas"].pop("hops"), "tasks.Cas.hops"),
                               (lambda r: r["tasks"]["Abs"]["hops"]["2"].update(n=29), "tasks.Abs.hops"),
                               (lambda r: (r["tasks"]["Abs"]["hops"]["1"].update(n=99),
                                           r["tasks"]["Abs"]["hops"]["2"].update(n=31)), "tasks.Abs.hops n must be")):
            result = copy.deepcopy(scored_result())
            mutate(result)
            self.assertTrue(any(needle in e for e in meme.contract_errors(result)), needle)

    def test_wiring_only_result_needs_no_run_disclosures(self):
        result = scored_result()
        for key in ("embedding_model", "arm", "maturation", "automem", "usage"):
            result.pop(key)
        result["run_status"] = "wiring_only"
        for row in result["tasks"].values():
            row["accuracy"] = None
        result["overall"]["macro_mean"] = None
        self.assertEqual(meme.contract_errors(result), [])

    def test_malformed_values_are_reported_not_raised(self):
        for mutate in (lambda r: r["tasks"]["ER"].update(accuracy=None), lambda r: r["tasks"]["ER"].update(accuracy="0.5"),
                       lambda r: r["tasks"]["ER"].update(accuracy=True), lambda r: r["tasks"]["ER"].pop("accuracy"),
                       lambda r: r["tasks"].update(Cas=[]), lambda r: r["tasks"]["Del"].update(pass_types="x"),
                       lambda r: r["tasks"]["Cas"].update(hops=[1, 2]), lambda r: r.update(overall=None),
                       lambda r: r.update(automem="0123abc"), lambda r: r["dataset"].update(episodes="100")):
            result = copy.deepcopy(scored_result())
            mutate(result)
            self.assertTrue(meme.contract_errors(result))

    def test_pass_types_must_be_non_negative_integers(self):
        for kinds in ({"real_pass": 5, "trivial_pass": -1, "knew_but_failed": 0, "never_knew": 160},
                      {"real_pass": 5, "trivial_pass": 0.5, "knew_but_failed": 0.5, "never_knew": 158},
                      {"real_pass": 5, "trivial_pass": 1, "never_knew": 158}):
            result = scored_result()
            result["tasks"]["Cas"]["pass_types"] = kinds
            self.assertTrue(any("tasks.Cas.pass_types" in e for e in meme.contract_errors(result)), kinds)

    def test_subset_denominators_follow_the_selected_episodes(self):
        self.assertEqual(meme.contract_errors(scored_result(subset=True)), [])
        for task, n, needle in (("ER", 100, "20-episode subset uses 20"), ("Del", 19, "tasks.Del.n=19"),
                                ("Cas", 41, "uses 20-40"), ("Abs", 19, "tasks.Abs.n=19")):
            result = scored_result(subset=True)
            result["tasks"][task] = task_row(task, 2, n, SUBSET_HOPS.get(task) and (n - 5, 5))
            self.assertTrue(any(needle in e for e in meme.contract_errors(result)), (task, n))
        for task, (first, second) in (("Cas", (0, 30)), ("Cas", (19, 11)), ("Abs", (20, 21)), ("Abs", (25, 0))):
            result = scored_result(subset=True)  # sums still match the task row, only the hop split is impossible
            row, hop1_correct = result["tasks"][task], min(2, first)
            row["hops"] = {"1": {"correct": hop1_correct, "n": first}, "2": {"correct": 2 - hop1_correct, "n": second}}
            row["n"], row["accuracy"] = first + second, round(2 / (first + second), 6)
            row["pass_types"]["never_knew"] = first + second - 3
            self.assertTrue(any(f"tasks.{task}.hops n: a 20-episode subset" in e for e in meme.contract_errors(result)),
                            (task, first, second))
        result = scored_result(subset=True)
        result["dataset"]["subset"] = False
        self.assertTrue(any("dataset.subset" in e for e in meme.contract_errors(result)))
        result = scored_result()
        result["dataset"]["subset"] = True
        self.assertTrue(any("dataset.subset" in e for e in meme.contract_errors(result)))


if __name__ == "__main__":
    unittest.main()
