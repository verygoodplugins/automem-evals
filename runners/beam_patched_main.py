#!/usr/bin/env python3
"""
BEAM entry point with timeout monkey-patched.

Upstream `benchmarks.common.llm_client.LLMClient` hardcodes a 120s request
timeout and exposes no CLI override. On local inference (Ollama / Qwen MoE
or Llama 3.3 70B with 32K context), single calls regularly exceed 120s even
on M5 Max. Without a longer budget, every call hits the 5-retry loop and
the question is scored as "no answer" — smoke runs produce all-zero noise
and can't tell us if the model is actually any good.

This wrapper patches the default timeout before BEAM imports LLMClient, then
hands control to upstream's main as if we'd invoked it directly.

Env vars:
  BEAM_LLM_TIMEOUT       Per-call timeout in seconds (default: 900).
  BEAM_LLM_CONNECT_TIMEOUT  Connect phase only (default: 20).

Everything else is pass-through: argv flows to `benchmarks.beam.run` unchanged.
"""

from __future__ import annotations

import os
import pathlib
import sys

# Put the submodule on the import path before anything else touches it.
REPO = pathlib.Path(__file__).resolve().parent.parent
UPSTREAM = REPO / "third_party" / "memory-benchmarks"
sys.path.insert(0, str(UPSTREAM))

BEAM_LLM_TIMEOUT = float(os.environ.get("BEAM_LLM_TIMEOUT", "900"))
BEAM_LLM_CONNECT_TIMEOUT = float(os.environ.get("BEAM_LLM_CONNECT_TIMEOUT", "20"))

import openai  # noqa: E402
from benchmarks.common import llm_client  # noqa: E402

_orig_init = llm_client.LLMClient.__init__


def _patched_init(self, *args, **kwargs):
    # Bump the default timeout both at the asyncio.wait_for layer (self.timeout)
    # and at the openai client-level (client_kwargs["timeout"]).
    kwargs.setdefault("timeout", BEAM_LLM_TIMEOUT)
    _orig_init(self, *args, **kwargs)
    # Rebuild the underlying client's openai.Timeout to match if the caller
    # didn't already pass a custom one.
    if hasattr(self, "_client") and self._client is not None:
        try:
            self._client = self._client.with_options(
                timeout=openai.Timeout(BEAM_LLM_TIMEOUT, connect=BEAM_LLM_CONNECT_TIMEOUT)
            )
        except Exception:
            pass


llm_client.LLMClient.__init__ = _patched_init  # type: ignore[method-assign]

print(
    f"[beam_patched_main] timeout={BEAM_LLM_TIMEOUT}s connect={BEAM_LLM_CONNECT_TIMEOUT}s",
    file=sys.stderr,
    flush=True,
)

# Now hand off to upstream's CLI main — it re-parses sys.argv itself.
from benchmarks.beam.run import main  # noqa: E402

if __name__ == "__main__":
    main()
