import os
import sys
from pathlib import Path

# repo root (parents[2] of tests/matrix/conftest.py) → runners/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# automem lab primitives importable (single source of truth for scoring)
_here = Path(__file__).resolve()
_candidates = [_here.parents[3] / "automem", Path.home() / "Projects" / "OpenAI" / "automem"]
_default = next((str(c) for c in _candidates if (c / "automem").is_dir()), str(_candidates[0]))
_automem = os.environ.get("AUTOMEM_DIR", _default)
sys.path.insert(0, str(Path(_automem) / "scripts" / "lab"))
