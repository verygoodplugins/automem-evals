import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matrix_stack as ms


class MatrixStackTests(unittest.TestCase):
    def test_slugify_label(self):
        self.assertEqual(ms.slugify_label("Candidate DB"), "candidate-db")
        self.assertEqual(ms.project_name("Candidate DB"), "automem_eval_candidate_db")

    def test_default_ports_offset_from_api_port(self):
        self.assertEqual(
            ms.default_ports(8011),
            {
                "api": 8011,
                "falkor": 6389,
                "falkor_ui": 3010,
                "qdrant": 6343,
            },
        )

    def test_render_override_contains_port_mappings(self):
        text = ms.render_override(
            {"api": 8011, "falkor": 6389, "falkor_ui": 3010, "qdrant": 6343}
        )
        self.assertIn('"8011:8001"', text)
        self.assertIn('"6389:6379"', text)
        self.assertIn('"3010:3000"', text)
        self.assertIn('"6343:6333"', text)

    def test_compose_up_command(self):
        cmd = ms.compose_command(
            "up",
            Path("/repo/automem"),
            Path("/tmp/override.yml"),
            "Candidate DB",
        )
        self.assertEqual(
            cmd,
            [
                "docker",
                "compose",
                "-p",
                "automem_eval_candidate_db",
                "-f",
                "/repo/automem/docker-compose.yml",
                "-f",
                "/tmp/override.yml",
                "up",
                "-d",
            ],
        )


if __name__ == "__main__":
    unittest.main()
