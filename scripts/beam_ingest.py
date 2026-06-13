#!/usr/bin/env python3
"""Wrapper for `python3 runners/beam_retrieval_eval.py ingest`."""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "runners"))

import beam_retrieval_eval  # noqa: E402


if __name__ == "__main__":
    sys.exit(beam_retrieval_eval.main(["ingest", *sys.argv[1:]]))
