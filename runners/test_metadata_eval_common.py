import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metadata_eval_common as mec


class MetadataExtractionTests(unittest.TestCase):
    def test_slugify_normalizes_metadata_values(self):
        self.assertEqual(mec.slugify_value("Agent Hub Developer"), "agent-hub-developer")
        self.assertEqual(mec.slugify_value("verygoodplugins/automem"), "verygoodplugins-automem")
        self.assertEqual(mec.slugify_value("  A__B...C  "), "a-b-c")

    def test_extract_signals_whitelist_skip_people_and_cap_tags(self):
        memory = {
            "id": "m1",
            "content": "A memory about local recall quality.",
            "tags": ["automem-evals"],
            "metadata": {
                "source_agent": "hub-developer",
                "provider": "voyage",
                "original_content": "must not be indexed",
                "trigger": "x" * 200,
                "entities": {
                    "people": ["Jack"],
                    "organizations": ["OpenAI"],
                    "tools": ["Qdrant"],
                },
            },
        }

        signals = mec.extract_metadata_signals(memory, max_tags=3)
        tags = [signal.tag for signal in signals]

        self.assertEqual(tags[:3], [
            "metadata-source-agent-hub-developer",
            "metadata-provider-voyage",
            "metadata-entities-organizations-openai",
        ])
        self.assertNotIn("metadata-original-content-must-not-be-indexed", tags)
        self.assertFalse(any("jack" in tag for tag in tags))
        self.assertFalse(any("trigger" in tag for tag in tags))
        self.assertLessEqual(len(tags), 3)

    def test_people_entities_are_opt_in(self):
        memory = {
            "id": "m1",
            "content": "A memory.",
            "tags": [],
            "metadata": {"entities": {"people": ["Ada Lovelace"]}},
        }
        self.assertEqual(mec.extract_metadata_signals(memory), [])
        opted_in = mec.extract_metadata_signals(memory, include_people=True)
        self.assertEqual(opted_in[0].tag, "metadata-entities-people-ada-lovelace")

    def test_compact_metadata_excerpt_uses_eligible_values_only(self):
        memory = {
            "metadata": {
                "source": "codex",
                "model": "gpt-5",
                "enrichment": {"semantic_neighbors": ["nope"]},
                "original_content": "hidden",
                "entities": {"organizations": ["AutoMem"], "people": ["Jack"]},
            }
        }
        excerpt = mec.compact_metadata_excerpt(memory)
        self.assertEqual(excerpt, "source: codex; model: gpt-5; entities.organizations: AutoMem")

    def test_value_absence_checks_content_and_tags(self):
        self.assertFalse(
            mec.metadata_value_is_hidden(
                "hub-developer",
                "The hub developer already appears here.",
                [],
            )
        )
        self.assertFalse(
            mec.metadata_value_is_hidden(
                "hub-developer",
                "Unrelated content",
                ["metadata-source-agent-hub-developer"],
            )
        )
        self.assertTrue(
            mec.metadata_value_is_hidden(
                "hub-developer",
                "Unrelated content",
                ["source-agent"],
            )
        )

    def test_vector_hash_is_stable(self):
        a = mec.hash_vector([0.1, 2, -3.5])
        b = mec.hash_vector([0.1, 2.0, -3.5])
        self.assertEqual(a, b)
        self.assertNotEqual(a, mec.hash_vector([0.1, 2.0, -3.4]))

    def test_parse_metadata_handles_json_strings(self):
        self.assertEqual(mec.parse_metadata(json.dumps({"source": "codex"})), {"source": "codex"})
        self.assertEqual(mec.parse_metadata("not-json"), {})


if __name__ == "__main__":
    unittest.main()
