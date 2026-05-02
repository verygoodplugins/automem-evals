import importlib.util
import sys
import unittest
from pathlib import Path


def load_script(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SeedFromSnapshotManifestOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_from_snapshot")

    def test_default_manifest_output(self):
        self.assertEqual(self.mod.resolve_manifest_output(None), self.mod.MANIFEST)

    def test_bare_manifest_filename_lands_under_seed_memories(self):
        path = self.mod.resolve_manifest_output("corpus_v1-8011.manifest.json")
        self.assertEqual(
            path,
            self.mod.HERE
            / "data"
            / "seed_memories"
            / "corpus_v1-8011.manifest.json",
        )

    def test_explicit_relative_path_is_preserved(self):
        self.assertEqual(
            self.mod.resolve_manifest_output("tmp/out.manifest.json"),
            Path("tmp/out.manifest.json"),
        )


class SeedCorpusManifestOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_corpus")

    def test_default_manifest_output(self):
        default = Path("/tmp/default.manifest.json")
        self.assertEqual(self.mod.resolve_manifest_output(None, default), default)

    def test_bare_manifest_filename_lands_under_seed_memories(self):
        default = Path("/tmp/default.manifest.json")
        path = self.mod.resolve_manifest_output("corpus_v2-8011.manifest.json", default)
        self.assertEqual(
            path,
            self.mod.HERE
            / "data"
            / "seed_memories"
            / "corpus_v2-8011.manifest.json",
        )

    def test_absolute_path_is_preserved(self):
        default = Path("/tmp/default.manifest.json")
        self.assertEqual(
            self.mod.resolve_manifest_output("/tmp/out.manifest.json", default),
            Path("/tmp/out.manifest.json"),
        )


if __name__ == "__main__":
    unittest.main()
