import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WRIT_DIR = ROOT / "third_party" / "writ"
ADAPTER_TEST = ROOT / "runners" / "writ" / "automem-adapter" / "automem.test.ts"


class WritAutoMemAdapterTypeScriptTests(unittest.TestCase):
    def test_adapter_typescript_unit_tests(self):
        if shutil.which("npx") is None:
            self.skipTest("npx is not available")
        if not (WRIT_DIR / "package.json").exists():
            self.skipTest("third_party/writ is not initialized")

        result = subprocess.run(
            ["npx", "--no-install", "tsx", str(ADAPTER_TEST)],
            cwd=WRIT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
