import importlib.util
import sys
import unittest
from pathlib import Path

# seed_from_snapshot / seed_corpus import seed_rebase from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


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

    def test_default_snapshot_is_v1(self):
        self.assertEqual(self.mod.resolve_snapshot(None), self.mod.SNAPSHOT)
        self.assertEqual(
            self.mod.default_manifest_for(self.mod.SNAPSHOT), self.mod.MANIFEST
        )

    def test_bare_snapshot_filename_reads_from_seed_memories(self):
        self.assertEqual(
            self.mod.resolve_snapshot("corpus_v2.embedded.jsonl"),
            self.mod.HERE / "data" / "seed_memories" / "corpus_v2.embedded.jsonl",
        )

    def test_explicit_snapshot_path_is_preserved(self):
        self.assertEqual(
            self.mod.resolve_snapshot("/tmp/rebased/corpus_v2.embedded.jsonl"),
            Path("/tmp/rebased/corpus_v2.embedded.jsonl"),
        )

    def test_v2_snapshot_defaults_to_v2_manifest_not_v1(self):
        snapshot = self.mod.resolve_snapshot("corpus_v2.embedded.jsonl")
        self.assertEqual(
            self.mod.resolve_manifest_output(None, self.mod.default_manifest_for(snapshot)),
            self.mod.HERE / "data" / "seed_memories" / "corpus_v2.manifest.json",
        )


class SeedAssociationsManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_script("seed_associations")

    def test_default_manifest(self):
        self.assertEqual(self.mod.resolve_manifest(None), self.mod.MANIFEST)

    def test_bare_manifest_filename_reads_from_seed_memories(self):
        self.assertEqual(
            self.mod.resolve_manifest("corpus_v1-8011.manifest.json"),
            self.mod.HERE / "data" / "seed_memories" / "corpus_v1-8011.manifest.json",
        )

    def test_absolute_path_is_preserved(self):
        self.assertEqual(
            self.mod.resolve_manifest("/tmp/x.manifest.json"),
            Path("/tmp/x.manifest.json"),
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
