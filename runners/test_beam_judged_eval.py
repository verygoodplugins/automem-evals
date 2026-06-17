"""No-network unit tests for the judged BEAM harness + time_anchor ingest fix.

Proxy-side tests (time_anchor parsing, timestamped chunking, batch body) need no
third-party deps. The scorer/adapter tests import ``beam_judged_eval``, which pulls
the official BEAM submodule prompts + LLMClient (aiolimiter/openai); run this with
the upstream deps available, e.g. ``.venv-beam/bin/python runners/test_beam_judged_eval.py``.
"""

import argparse
import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import beam_retrieval_eval as beam  # dependency-free

try:
    import beam_judged_eval as bj

    BJ_AVAILABLE = True
    BJ_ERR = ""
except Exception as exc:  # noqa: BLE001
    bj = None
    BJ_AVAILABLE = False
    BJ_ERR = f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Proxy: time_anchor parsing + timestamped chunking + batch passthrough
# ---------------------------------------------------------------------------


class TimeAnchorTests(unittest.TestCase):
    def test_parses_beam_and_iso_formats(self):
        self.assertEqual(beam.parse_time_anchor("March-15-2024").date().isoformat(), "2024-03-15")
        self.assertEqual(beam.parse_time_anchor("Mar 15 2024").date().isoformat(), "2024-03-15")
        self.assertEqual(beam.parse_time_anchor("2024-03-15").date().isoformat(), "2024-03-15")

    def test_returns_none_for_missing_or_junk(self):
        self.assertIsNone(beam.parse_time_anchor(None))
        self.assertIsNone(beam.parse_time_anchor(""))
        self.assertIsNone(beam.parse_time_anchor("not a date"))


class TimestampedChunkingTests(unittest.TestCase):
    def _conv(self):
        row = {
            "conversation_id": "c1",
            "chat": [
                [
                    {"id": 1, "role": "user", "content": "a", "time_anchor": "March-15-2024"},
                    {"id": 2, "role": "assistant", "content": "b"},  # no anchor -> carry forward
                    {"id": 3, "role": "user", "content": "c", "time_anchor": "March-20-2024"},
                ]
            ],
            "probing_questions": {},
        }
        return beam.normalize_conversation(row, tier="100K", conversation_idx=0)

    def test_with_timestamps_sets_monotonic_dates(self):
        chunks = beam.build_memory_chunks(self._conv(), run_id="t", with_timestamps=True)
        ts = [c.timestamp for c in chunks]
        self.assertTrue(all(ts), "every chunk should get a timestamp")
        self.assertEqual(ts, sorted(ts), "timestamps must be strictly monotonic in turn order")
        self.assertEqual(ts[0][:10], "2024-03-15")
        self.assertEqual(ts[1][:10], "2024-03-15")  # carried forward
        self.assertEqual(ts[2][:10], "2024-03-20")

    def test_default_leaves_timestamps_none(self):
        chunks = beam.build_memory_chunks(self._conv(), run_id="t")
        self.assertTrue(all(c.timestamp is None for c in chunks))

    def test_store_batch_includes_timestamp_only_when_set(self):
        captured = {}

        def fake_req(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            captured["body"] = body
            return {"memory_ids": [f"id{i}" for i in range(len(body["memories"]))]}

        client = beam.AutoMemClient("http://localhost:8001", "t", request_json=fake_req)
        with_ts = beam.MemoryChunk(
            key="k", content="x", tags=["beam"], metadata={}, sequence=0,
            conversation_id="c1", timestamp="2024-03-15T00:00:00+00:00",
        )
        client.store_memory_batch([with_ts])
        self.assertEqual(
            captured["body"]["memories"][0]["timestamp"], "2024-03-15T00:00:00+00:00"
        )

        without_ts = beam.MemoryChunk(
            key="k", content="x", tags=["beam"], metadata={}, sequence=0, conversation_id="c1"
        )
        client.store_memory_batch([without_ts])
        self.assertNotIn("timestamp", captured["body"]["memories"][0])


# ---------------------------------------------------------------------------
# Judged harness: adapter, ported scorers, evaluate_question
# ---------------------------------------------------------------------------


class _StubAnswerer:
    def __init__(self, text):
        self.text = text

    async def generate(self, system, user, **kw):
        return self.text


class _StubJudge:
    """Branches on the system prompt to serve nugget / extract / align calls."""

    def __init__(self, nugget_score=1.0, events=None, align=None):
        self.nugget_score = nugget_score
        self.events = events or []
        self.align = list(align or [])

    async def generate_structured(self, system, user, **kw):
        if system.startswith("Extract events"):
            return {"events": self.events}
        if system.startswith("Align"):
            return {"index": self.align.pop(0) if self.align else -1}
        return {"score": self.nugget_score, "reason": "stub"}


@unittest.skipUnless(BJ_AVAILABLE, f"beam_judged_eval import failed: {BJ_ERR}")
class AdapterTests(unittest.TestCase):
    def test_to_answer_memories_sorts_and_resolves_created_at(self):
        resp = {
            "results": [
                {
                    "memory": {"id": "m1", "content": "hello", "timestamp": "2024-03-15T00:00:00+00:00", "metadata": {}},
                    "score": 0.2,
                },
                {
                    "memory": {"id": "m2", "content": "world", "metadata": {"time_anchor": "March-20-2024"}},
                    "score": 0.9,
                },
            ]
        }
        mems = bj.to_answer_memories(resp)
        self.assertEqual(mems[0]["id"], "m2")  # higher score first
        self.assertEqual(mems[0]["memory"], "world")
        self.assertEqual(mems[0]["created_at"][:10], "2024-03-20")  # fallback from time_anchor
        self.assertEqual(mems[1]["created_at"][:10], "2024-03-15")


@unittest.skipUnless(BJ_AVAILABLE, f"beam_judged_eval import failed: {BJ_ERR}")
class RetrievalDiagnosticsTests(unittest.TestCase):
    def _q(self, sources):
        return beam.BeamQuestion(
            question_id="q", question_type="information_extraction",
            question="when?", rubric=["nugget"], source_chat_ids=sources,
        )

    def test_source_hit_true_within_cutoff(self):
        resp = {"results": [
            {"memory": {"content": "[chat_id=42] x", "metadata": {"source_chat_ids": [42]}}, "score": 0.9},
            {"memory": {"content": "[chat_id=7] y", "metadata": {"source_chat_ids": [7]}}, "score": 0.5},
        ]}
        diag = bj.retrieval_diagnostics(resp, self._q([42]), cutoff=10)
        self.assertTrue(diag["source_chat_hit"])
        self.assertEqual(diag["n_source"], 1)

    def test_source_miss_and_none_when_no_source(self):
        resp = {"results": [{"memory": {"content": "[chat_id=7] y", "metadata": {"source_chat_ids": [7]}}, "score": 0.5}]}
        self.assertFalse(bj.retrieval_diagnostics(resp, self._q([42]), cutoff=10)["source_chat_hit"])
        self.assertIsNone(bj.retrieval_diagnostics(resp, self._q([]), cutoff=10)["source_chat_hit"])

    def test_cutoff_excludes_deeper_hit(self):
        resp = {"results": [
            {"memory": {"content": "[chat_id=1] a"}, "score": 0.9},
            {"memory": {"content": "[chat_id=42] b", "metadata": {"source_chat_ids": [42]}}, "score": 0.4},
        ]}
        self.assertFalse(bj.retrieval_diagnostics(resp, self._q([42]), cutoff=1)["source_chat_hit"])


@unittest.skipUnless(BJ_AVAILABLE, f"beam_judged_eval import failed: {BJ_ERR}")
class ScorerTests(unittest.TestCase):
    def test_count_tokens(self):
        self.assertGreater(bj._count_tokens("hello world this is a test prompt"), 0)
        self.assertGreater(bj._count_tokens("x " * 2000), bj._count_tokens("short"))

    def test_cutoff_label_and_clamp(self):
        self.assertEqual(bj.cutoff_label(100), "top_100")
        self.assertEqual(bj.cutoff_label(None), "all")
        self.assertEqual(bj._clamp_nugget_score(0.8), 1.0)
        self.assertEqual(bj._clamp_nugget_score(0.5), 0.5)
        self.assertEqual(bj._clamp_nugget_score(0.1), 0.0)

    def test_kendall_tau_b_extremes(self):
        self.assertEqual(bj.compute_kendall_tau_b([0, 1, 2, 3], [0, 1, 2, 3]), 1.0)
        self.assertEqual(bj.compute_kendall_tau_b([3, 2, 1, 0], [0, 1, 2, 3]), -1.0)

    def test_compute_beam_metrics_threshold_and_per_type(self):
        evals = [
            {"question_type": "abstention", "cutoff_results": {"top_100": {"score": 1.0}}},
            {"question_type": "abstention", "cutoff_results": {"top_100": {"score": 0.0}}},
            {"question_type": "summarization", "cutoff_results": {"top_100": {"score": 0.5}}},
        ]
        m = bj.compute_beam_metrics(evals, [100])["top_100"]
        self.assertEqual(m["overall"]["total"], 3)
        self.assertEqual(m["overall"]["correct"], 2)  # 1.0 and 0.5 pass (>=0.5)
        self.assertAlmostEqual(m["overall"]["accuracy"], 200 / 3)
        self.assertEqual(m["by_question_type"]["abstention"]["correct"], 1)
        self.assertEqual(m["by_question_type"]["summarization"]["correct"], 1)

    def test_build_ranking(self):
        ns = argparse.Namespace(recency_bias="auto", min_score=None)
        self.assertEqual(bj.build_ranking(ns), {"recency_bias": "auto"})
        ns = argparse.Namespace(recency_bias="off", min_score=0.4)
        self.assertEqual(bj.build_ranking(ns), {"min_score": 0.4})
        ns = argparse.Namespace(recency_bias="off", min_score=None)
        self.assertEqual(bj.build_ranking(ns), {})


@unittest.skipUnless(BJ_AVAILABLE, f"beam_judged_eval import failed: {BJ_ERR}")
class EvaluateQuestionTests(unittest.TestCase):
    def _question(self, qtype, rubric):
        return beam.BeamQuestion(
            question_id="100K_0_q0_" + qtype,
            question_type=qtype,
            question="When did X happen?",
            rubric=rubric,
            source_chat_ids=[1],
        )

    def test_nugget_mean_and_pass(self):
        q = self._question("information_extraction", ["nugget A", "nugget B"])
        mems = [{"memory": "X happened in March", "created_at": "2024-03-15T00:00:00+00:00", "score": 0.9, "id": "m1"}]
        ev = asyncio.run(
            bj.evaluate_question(
                q, mems, cutoffs=[100], answerer=_StubAnswerer("ANSWER: March"), judge=_StubJudge(1.0)
            )
        )
        cr = ev["cutoff_results"]["top_100"]
        self.assertEqual(cr["score"], 1.0)
        self.assertEqual(cr["judgment"], "PASS")
        self.assertEqual(len(cr["nugget_scores"]), 2)
        self.assertEqual(cr["generated_answer"], "March")  # ANSWER: prefix stripped
        self.assertGreater(cr["context_tokens"], 0)  # token instrumentation populated

    def test_event_ordering_adds_tau(self):
        q = self._question("event_ordering", ["e0", "e1", "e2"])
        mems = [{"memory": "stuff", "created_at": "2024-03-15T00:00:00+00:00", "score": 0.9, "id": "m1"}]
        judge = _StubJudge(nugget_score=1.0, events=["e0", "e1", "e2"], align=[0, 1, 2])
        ev = asyncio.run(
            bj.evaluate_question(q, mems, cutoffs=[100], answerer=_StubAnswerer("ans"), judge=judge)
        )
        cr = ev["cutoff_results"]["top_100"]
        self.assertIn("event_ordering", cr)
        self.assertEqual(cr["event_ordering"]["tau_b"], 1.0)
        self.assertEqual(cr["score_with_tau"], 1.0)  # (avg 1.0 + norm tau 1.0) / 2

    def test_missing_rubric_is_error(self):
        q = self._question("summarization", [])
        ev = asyncio.run(
            bj.evaluate_question(q, [], cutoffs=[100], answerer=_StubAnswerer("x"), judge=_StubJudge())
        )
        cr = ev["cutoff_results"]["top_100"]
        self.assertEqual(cr["judgment"], "ERROR")
        self.assertEqual(cr["score"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
