#!/usr/bin/env python3
"""Wrapper for `python3 runners/beam_judged_eval.py` (native judged BEAM harness).

Example (smoke):
    OPENAI_API_KEY=... python3 scripts/beam_judged.py \
        --sample-conversations 1 --answerer-model gpt-5-mini --judge-model gpt-5-mini

Example (headline 100K run, official default models):
    OPENAI_API_KEY=... python3 scripts/beam_judged.py \
        --tier 100K --answerer-model gpt-5 --judge-model gpt-5
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "runners"))

import beam_judged_eval  # noqa: E402


if __name__ == "__main__":
    sys.exit(beam_judged_eval.main(sys.argv[1:]))
