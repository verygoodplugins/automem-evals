import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from scripts.benchmarks.evalmem_diagnostic import defect_codes, summarize, validate_judge, main


class AttributionTests(unittest.TestCase):
    def test_correct_and_unjudged_answers_do_not_contribute_codes(self):
        for correct in (True, None):
            self.assertEqual(defect_codes(correct, "Miss", "Miss", "GF"), [])

    def test_encoding_masks_retrieval_but_not_oracle_generation(self):
        self.assertEqual(defect_codes(False, "Miss", "Miss", "GF"), ["EM", "GF"])
        self.assertEqual(defect_codes(False, "Exist", "Miss", "GRF"), ["RF", "GRF"])

    def test_unknown_store_does_not_become_missing_or_retrieval_failure(self):
        self.assertEqual(defect_codes(False, "Unknown", "Miss", "Pass"), [])

    def test_retrieval_hit_with_oracle_failure(self):
        self.assertEqual(defect_codes(False, "Exist", "Hit", "GF"), ["GF"])

    def test_full_query_denominator_and_layer_union(self):
        rows = [{"status": "scored", "correct": False, "defect_codes": ["RF", "GF", "GRF"]},
                {"status": "scored", "correct": True, "defect_codes": []}]
        self.assertEqual(summarize(rows)["rates"], {"encoding": 0, "retrieval": .5, "generation": .5})
        rows[0]["status"] = "not_scored"
        self.assertEqual(summarize(rows)["rates"], dict.fromkeys(("encoding", "retrieval", "generation")))
        self.assertEqual(summarize([])["status"], "not_scored")

    def test_bad_judge_boolean_or_state_is_rejected(self):
        valid = dict(correct=False, encoding="Exist", retrieval="Miss", generation="Pass", reason="missing")
        self.assertEqual(validate_judge(valid), valid)
        for key, value in (("correct", "false"), ("encoding", "unknown"), ("generation", "Fail")):
            with self.assertRaises(ValueError):
                validate_judge(dict(valid, **{key: value}))

    def test_graph_targets_are_deduplicated(self):
        from scripts.benchmarks.evalmem_diagnostic import client_expand
        response = {"results": [{"id": "seed", "relations": [
            {"type": "RELATES_TO", "strength": .8, "memory": {"id": "target"}},
            {"type": "RELATES_TO", "strength": .9, "memory": {"id": "target"}}]}]}
        self.assertEqual([r["id"] for r in client_expand(response)], ["target"])

    def test_nonlocal_endpoints_are_rejected_before_reads(self):
        with patch("sys.argv", ["evalmem", "--dataset", "unused", "--output", "unused",
                                "--endpoint", "https://automem.example"]):
            with self.assertRaises(SystemExit) as exc:
                main()
        self.assertEqual(exc.exception.code, 2)

    def test_offline_and_exhausted_judge_preserve_unknown_rates(self):
        for offline in (True, False):
            with self.subTest(offline=offline), tempfile.TemporaryDirectory() as tmp:
                dataset, output = Path(tmp) / "locomo10.json", Path(tmp) / "result.json"
                dataset.write_text(json.dumps([{"sample_id": "conv-26", "conversation": {
                    "session_1": [{"dia_id": "D1", "speaker": "A", "text": "Paris"}]},
                    "qa": [{"category": 1, "question": "Where?", "answer": "Paris", "evidence": ["D1"]}]}]))
                dataset.with_name("manifest.json").write_text(json.dumps({"scope_prefix": "run",
                    "conversations": {"conv-26": {"D1": "m1"}}}))
                memory = {"id": "m1", "content": "A: Paris", "tags": ["run:conv-26"],
                          "metadata": {"conversation_id": "conv-26", "dialog_id": "D1"}}

                def http(url, *args):
                    if offline:
                        self.fail("offline made an HTTP request")
                    if "/memory/" in url:
                        return {"memory": memory}
                    if "/recall?" in url:
                        return {"results": [{"id": "m1", "memory": {k: v for k, v in memory.items() if k != "id"}}]}
                    raise urllib.error.HTTPError(url, 429, "credits exhausted", {}, io.BytesIO())

                argv = ["evalmem", "--dataset", str(dataset), "--output", str(output), "--model"]
                with patch("sys.argv", argv + (["--offline"] if offline else [])), patch.dict(
                        "os.environ", {"OPENAI_API_KEY": "test"}), patch(
                        "scripts.benchmarks.evalmem_diagnostic.request", side_effect=http), contextlib.redirect_stdout(io.StringIO()):
                    main()
                result = json.loads(output.read_text())
                for arm in result["rows"]:
                    self.assertEqual(result["summaries"][arm]["status"], "not_scored")
                    self.assertTrue(all(v is None for v in result["summaries"][arm]["rates"].values()))
                    self.assertEqual(result["rows"][arm][0]["defect_codes"], [])


if __name__ == "__main__":
    unittest.main()
