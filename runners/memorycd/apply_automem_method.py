#!/usr/bin/env python3
"""Overlay AutoMemMethod onto a clean MemoryCD checkout.

Usage: python3 runners/memorycd/apply_automem_method.py /path/to/MemoryCD
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected text was not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_automem_method.py /path/to/MemoryCD")
    harness = Path(sys.argv[1]).resolve()
    if not (harness / "methods" / "base_method.py").is_file():
        raise SystemExit(f"Not a MemoryCD checkout: {harness}")
    source = Path(__file__).with_name("automem_method.py")
    shutil.copy2(source, harness / "methods" / "automem.py")
    shutil.copy2(Path(__file__).with_name("anthropic_compat.py"), harness / "anthropic_compat.py")
    replace_once(
        harness / "methods" / "__init__.py",
        "from .rag import RAGMethod\n",
        "from .rag import RAGMethod\nfrom .automem import AutoMemMethod\n",
    )
    replace_once(
        harness / "methods" / "__init__.py",
        '"BaseMethod", "LongContextMethod", "RAGMethod"]',
        '"BaseMethod", "LongContextMethod", "RAGMethod", "AutoMemMethod"]',
    )
    replace_once(
        harness / "eval_core.py",
        "from methods import BaseMethod, LongContextMethod, RAGMethod",
        "from methods import AutoMemMethod, BaseMethod, LongContextMethod, RAGMethod",
    )
    replace_once(
        harness / "api.py",
        'Provider = Literal["openai", "openrouter"]',
        'Provider = Literal["openai", "openrouter", "anthropic"]',
    )
    replace_once(
        harness / "api.py",
        '    if explicit in ("openai", "openrouter"):',
        '    if explicit in ("openai", "openrouter", "anthropic"):',
    )
    replace_once(
        harness / "api.py",
        '    if p == "openrouter":\n        api_key = os.getenv("OPENROUTER_API_KEY")',
        '    if p == "anthropic":\n        api_key = os.getenv("ANTHROPIC_API_KEY")\n        if not api_key:\n            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")\n        from anthropic_compat import AnthropicOpenAICompat\n        return AnthropicOpenAICompat(api_key), p\n    if p == "openrouter":\n        api_key = os.getenv("OPENROUTER_API_KEY")',
    )
    replace_once(
        harness / "eval_core.py",
        '    if method_name == "long_context":\n        return LongContextMethod(max_memory_items=max_memory_items)\n',
        '    if method_name == "automem":\n        return AutoMemMethod(max_memory_items=max_memory_items, dataset_name=dataset_name)\n    if method_name == "long_context":\n        return LongContextMethod(max_memory_items=max_memory_items)\n',
    )
    replace_once(
        harness / "eval_core.py",
        'Supported: long_context, rag.',
        'Supported: long_context, rag, automem.',
    )
    for name in ("evaluation_all_4task.py", "evaluation_all_4task_cross_domain.py"):
        replace_once(
            harness / name,
            'choices=["long_context", "rag"]',
            'choices=["long_context", "rag", "automem"]',
        )
    print(f"Applied AutoMemMethod overlay to {harness}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
