import os
import sys
from pathlib import Path

# matrix package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# automem lab primitives importable (single source of truth for scoring)
_default = "/Users/jgarturo/Projects/OpenAI/automem"
_automem = os.environ.get("AUTOMEM_DIR", _default)
sys.path.insert(0, str(Path(_automem) / "scripts" / "lab"))
