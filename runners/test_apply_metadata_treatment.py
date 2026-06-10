import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import apply_metadata_treatment as treatment


class MetadataTreatmentPlanTests(unittest.TestCase):
    def test_tag_treatment_preserves_existing_tags_and_content(self):
        memory = {
            "id": "m1",
            "content": "Recall quality note.",
            "tags": ["automem-evals", "metadata-source-agent-hub-developer"],
            "metadata": {"source_agent": "hub-developer", "provider": "voyage"},
        }

        update = treatment.build_tag_update(memory, max_tags=5)

        self.assertEqual(update["id"], "m1")
        self.assertEqual(update["content"], "Recall quality note.")
        self.assertEqual(
            update["tags"],
            ["automem-evals", "metadata-source-agent-hub-developer", "metadata-provider-voyage"],
        )
        self.assertIn("metadata-source-agent-hub-developer", update["tag_prefixes"])
        self.assertIn("metadata-provider-voyage", update["generated_tags"])
        self.assertNotIn("metadata-source-agent-hub-developer", update["generated_tags"])

    def test_tag_treatment_returns_none_when_no_new_tags(self):
        memory = {
            "id": "m1",
            "content": "Recall quality note.",
            "tags": ["metadata-provider-voyage"],
            "metadata": {"provider": "voyage"},
        }
        self.assertIsNone(treatment.build_tag_update(memory))

    def test_embedding_treatment_builds_augmented_text_without_mutating_graph_fields(self):
        memory = {
            "id": "m1",
            "content": "Recall quality note.",
            "tags": ["automem-evals"],
            "metadata": {"source": "codex", "model": "gpt-5"},
        }

        plan = treatment.build_embedding_update(memory)

        self.assertEqual(plan["id"], "m1")
        self.assertEqual(plan["content"], "Recall quality note.")
        self.assertEqual(plan["tags"], ["automem-evals"])
        self.assertEqual(
            plan["embedding_text"],
            "Recall quality note.\n\nMetadata: source: codex; model: gpt-5",
        )

    def test_embedding_treatment_skips_memories_without_eligible_metadata(self):
        memory = {
            "id": "m1",
            "content": "Recall quality note.",
            "tags": ["automem-evals"],
            "metadata": {"original_content": "skip"},
        }
        self.assertIsNone(treatment.build_embedding_update(memory))

    def test_db_target_guard_refuses_remote_hosts(self):
        with mock.patch.dict(
            "os.environ",
            {"FALKORDB_HOST": "remote.example.com", "QDRANT_URL": "http://localhost:6333"},
            clear=True,
        ):
            with self.assertRaises(SystemExit):
                treatment.assert_local_db_targets()

        with mock.patch.dict(
            "os.environ",
            {"FALKORDB_HOST": "localhost", "QDRANT_URL": "https://qdrant.example.com"},
            clear=True,
        ):
            with self.assertRaises(SystemExit):
                treatment.assert_local_db_targets()

    def test_tag_update_graph_rows_do_not_include_nested_metadata(self):
        class FakeGraph:
            def __init__(self):
                self.rows = None

            def query(self, _query, params):
                self.rows = params["rows"]

        class FakeQdrant:
            def __init__(self):
                self.payloads = []

            def set_payload(self, **kwargs):
                self.payloads.append(kwargs["payload"])

        graph = FakeGraph()
        qdrant = FakeQdrant()
        update = {
            "id": "m1",
            "tags": ["automem-evals", "metadata-provider-voyage"],
            "tag_prefixes": ["automem-evals", "metadata-provider-voyage"],
            "metadata": {"provider": "voyage"},
        }

        treatment.execute_tag_updates(graph, qdrant, "memories", [update], batch_size=1)

        self.assertEqual(graph.rows[0]["id"], "m1")
        self.assertNotIn("metadata", graph.rows[0])
        self.assertEqual(qdrant.payloads[0]["metadata"], {"provider": "voyage"})


if __name__ == "__main__":
    unittest.main()
