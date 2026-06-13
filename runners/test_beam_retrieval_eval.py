import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import beam_retrieval_eval as beam


class TierTests(unittest.TestCase):
    def test_normalize_tier_accepts_issue_aliases(self):
        self.assertEqual(beam.normalize_tier("100k"), "100K")
        self.assertEqual(beam.normalize_tier("128k"), "100K")
        self.assertEqual(beam.normalize_tier("1m"), "1M")
        self.assertEqual(beam.dataset_spec_for_tier("10m").repo, "Mohammadta/BEAM-10M")

    def test_normalize_tier_rejects_non_beam_10k(self):
        with self.assertRaises(ValueError):
            beam.normalize_tier("10k")

    def test_default_endpoint_is_localhost(self):
        self.assertEqual(beam.DEFAULT_ENDPOINT, "http://localhost:8001")
        self.assertTrue(beam.is_local_endpoint("http://127.0.0.1:8001"))
        self.assertFalse(beam.is_local_endpoint("https://automem.example.com"))


class DatasetNormalizationTests(unittest.TestCase):
    def test_python_literal_probing_questions_are_parsed(self):
        row = {
            "conversation_id": "conv-1",
            "chat": [[{"id": 1, "role": "user", "content": "I use Flask."}]],
            "probing_questions": "{'information_extraction': [{'question': 'What do I use?', 'rubric': ['Flask'], 'source_chat_ids': [1]}]}",
        }

        conversation = beam.normalize_conversation(row, tier="100K", conversation_idx=0)

        self.assertEqual(conversation.conversation_id, "conv-1")
        self.assertEqual(len(conversation.questions), 1)
        self.assertEqual(conversation.questions[0].question_type, "information_extraction")
        self.assertEqual(conversation.questions[0].source_chat_ids, [1])

    def test_source_chat_ids_are_extracted_from_common_shapes(self):
        self.assertEqual(
            beam.extract_source_chat_ids(
                {
                    "source_chat_ids": {"first": [58], "second": "chat_id: 24"},
                    "conversation_references": ["Session 66", "chat_id: 12"],
                }
            ),
            [12, 24, 58],
        )

    def test_source_chat_ids_match_runner_stored_equals_format(self):
        # The ingest path stores "chat_id=<n>" (equals) in the memory content
        # prefix, so the content-fallback extractor must parse that exact shape,
        # not only the "chat_id: <n>" (colon) form.
        self.assertEqual(
            beam.extract_source_chat_ids(
                {"conversation_references": "[BEAM 100K conv=Conv 1 chat_id=42 role=user] hi"}
            ),
            [42],
        )

    def test_source_ids_fall_back_to_content_when_metadata_absent(self):
        # Mirrors a recall result whose metadata was stripped: source IDs must
        # still be recovered from the stored "chat_id=<n>" content prefix.
        result = {
            "memory": {
                "id": "mem-1",
                "content": "[BEAM 100K conv=Conv 1 chat_id=24 role=user] The app uses Flask.",
            }
        }
        self.assertEqual(beam._source_ids_from_result(result), {24})


class ChunkTests(unittest.TestCase):
    def test_chunks_are_small_and_tagged_with_run_tier_and_conversation(self):
        conversation = beam.normalize_conversation(
            {
                "conversation_id": "Conv 1",
                "chat": [
                    [
                        {
                            "id": 7,
                            "role": "user",
                            "content": "A" * 900,
                            "time_anchor": "March-15-2024",
                        }
                    ]
                ],
                "probing_questions": {},
            },
            tier="100K",
            conversation_idx=0,
        )

        chunks = beam.build_memory_chunks(conversation, run_id="abc123", max_chars=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.content) <= 500 for chunk in chunks))
        self.assertEqual(
            chunks[0].tags,
            ["beam", "beam-run-abc123", "beam-tier-100k", "beam-conv-conv-1"],
        )
        self.assertEqual(chunks[0].metadata["source_chat_ids"], [7])
        self.assertEqual(chunks[0].metadata["time_anchor"], "March-15-2024")


class ScoringTests(unittest.TestCase):
    def test_rubric_overlap_scores_matching_evidence(self):
        score = beam.score_rubric_overlap(
            ["The response should mention Flask login integration"],
            ["chat_id=3: Flask-Login v0.6.2 was integrated for session management."],
        )

        self.assertGreaterEqual(score, 0.4)

    def test_abstention_scores_absent_evidence(self):
        self.assertTrue(
            beam.score_abstention_evidence_absence(
                ["No information about the user's background is present"],
                ["chat_id=1: The user asked for a project schedule."],
            )
        )

    def test_score_question_uses_source_chat_hit_and_rubric_overlap(self):
        question = beam.BeamQuestion(
            question_id="100K_0_q0_information_extraction",
            question_type="information_extraction",
            question="Which framework did I use?",
            rubric=["Flask"],
            source_chat_ids=[24],
            difficulty="easy",
        )
        recall_response = {
            "results": [
                {
                    "id": "mem-1",
                    "memory": {
                        "id": "mem-1",
                        "content": "chat_id=24: The app uses Flask routes.",
                        "metadata": {"source_chat_ids": [24]},
                    },
                    "final_score": 0.9,
                }
            ]
        }

        result = beam.score_question(question, recall_response)

        self.assertTrue(result["metrics"]["source_chat_hit"])
        self.assertGreater(result["metrics"]["rubric_overlap"], 0)
        self.assertGreaterEqual(result["metrics"]["proxy_score"], 0.5)


class ClientRequestTests(unittest.TestCase):
    def test_store_memory_batch_uses_batch_endpoint_and_payload(self):
        calls = []

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            calls.append((method, path, params, body))
            return {"memory_ids": ["mem-1"], "stored": 1}

        client = beam.AutoMemClient(
            "http://localhost:8001",
            "test-token",
            request_json=fake_request,
        )
        ids = client.store_memory_batch(
            [
                beam.MemoryChunk(
                    key="chunk-1",
                    content="chat_id=1: hello",
                    tags=["beam"],
                    metadata={"source_chat_ids": [1]},
                    sequence=0,
                    conversation_id="conv-1",
                )
            ]
        )

        self.assertEqual(ids, ["mem-1"])
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/memory/batch")
        self.assertEqual(calls[0][3]["memories"][0]["content"], "chat_id=1: hello")

    def test_associate_sequential_chunks_batches_occurred_before_edges(self):
        bodies = []

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            bodies.append(body)
            return {"status": "success", "created_count": len(body["associations"])}

        client = beam.AutoMemClient(
            "http://localhost:8001",
            "test-token",
            request_json=fake_request,
        )

        created = client.associate_sequential_chunks(["m1", "m2", "m3"])

        self.assertEqual(created, 2)
        self.assertEqual(bodies[0]["associations"][0]["type"], "OCCURRED_BEFORE")
        self.assertEqual(bodies[0]["associations"][0]["memory1_id"], "m1")
        self.assertEqual(bodies[0]["associations"][1]["memory2_id"], "m3")

    def test_association_batch_falls_back_to_single_calls_for_old_servers(self):
        calls = []

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            calls.append(body)
            if "associations" in body:
                raise beam.AutoMemRequestError(400, "BAD REQUEST", "'memory1_id' and 'memory2_id' are required")
            return {"memory1_id": body["memory1_id"], "memory2_id": body["memory2_id"]}

        client = beam.AutoMemClient(
            "http://localhost:8001",
            "test-token",
            request_json=fake_request,
        )

        created = client.associate_sequential_chunks(["m1", "m2", "m3"])

        self.assertEqual(created, 2)
        self.assertEqual(calls[1]["memory1_id"], "m1")
        self.assertEqual(calls[2]["memory2_id"], "m3")

    def test_cleanup_deletes_recalled_run_tag_ids(self):
        deleted = []
        pages = [
            [{"id": "mem-1"}, {"memory": {"id": "mem-2"}}],
            [],
        ]

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            if method == "GET":
                self.assertEqual(params["tags"], ["beam-run-abc123"])
                self.assertEqual(params["tag_match"], "exact")
                return {"results": pages.pop(0)}
            deleted.append(path)
            return {}

        client = beam.AutoMemClient(
            "http://localhost:8001",
            "test-token",
            request_json=fake_request,
        )

        self.assertEqual(client.cleanup_run("abc123"), 2)
        self.assertEqual(deleted, ["/memory/mem-1", "/memory/mem-2"])

    def test_cleanup_continues_until_recall_returns_empty(self):
        deleted = []
        pages = [
            [{"id": "mem-1"}],
            [{"id": "mem-2"}],
            [],
        ]

        def fake_request(endpoint, token, method, path, *, params=None, body=None, timeout=60):
            if method == "GET":
                return {"results": pages.pop(0)}
            deleted.append(path)
            return {}

        client = beam.AutoMemClient(
            "http://localhost:8001",
            "test-token",
            request_json=fake_request,
        )

        self.assertEqual(client.cleanup_run("abc123"), 2)
        self.assertEqual(deleted, ["/memory/mem-1", "/memory/mem-2"])


class ReportTests(unittest.TestCase):
    def test_aggregate_includes_all_ten_ability_categories(self):
        aggregate = beam.aggregate_results([])

        self.assertEqual(set(aggregate["by_question_type"]), set(beam.BEAM_QUESTION_TYPES))
        self.assertEqual(aggregate["by_question_type"]["abstention"]["total"], 0)

    def test_wrapper_entrypoints_are_present(self):
        repo = pathlib.Path(__file__).resolve().parent.parent
        self.assertTrue((repo / "scripts" / "beam_ingest.py").exists())
        self.assertTrue((repo / "scripts" / "beam_eval.py").exists())
        self.assertTrue((repo / "scripts" / "beam_report.py").exists())
        self.assertTrue((repo / "scripts" / "beam_cleanup.py").exists())


class CleanupCommandTests(unittest.TestCase):
    def test_cleanup_command_does_not_rewrite_results_or_report(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            manifest_path = run_dir / "manifest.json"
            results_path = run_dir / "results.json"
            report_path = run_dir / "report.md"
            manifest_path.write_text(
                '{"run_id":"run-1","run_tag":"beam-run-run-1","conversations":[]}'
            )
            results_path.write_text("original results")
            report_path.write_text("original report")
            calls = []

            class FakeClient:
                def __init__(self, endpoint, token):
                    self.endpoint = endpoint
                    self.token = token

                def cleanup_run(self, run_id):
                    calls.append(run_id)
                    return 3

            original = beam.AutoMemClient
            try:
                beam.AutoMemClient = FakeClient
                rc = beam.main(
                    [
                        "cleanup",
                        "--manifest",
                        str(manifest_path),
                        "--endpoint",
                        "http://localhost:8001",
                    ]
                )
            finally:
                beam.AutoMemClient = original

            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["run-1"])
            self.assertEqual(results_path.read_text(), "original results")
            self.assertEqual(report_path.read_text(), "original report")


if __name__ == "__main__":
    unittest.main()
