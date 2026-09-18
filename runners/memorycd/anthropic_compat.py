"""Small OpenAI-chat-shaped wrapper used by the optional MemoryCD overlay."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List


class AnthropicOpenAICompat:
    """Expose ``chat.completions.create`` for MemoryCD's existing predictor."""

    def __init__(self, api_key: str) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError("Anthropic provider requires: pip install anthropic") from exc
        self._client = Anthropic(api_key=api_key)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, *, messages: List[Dict[str, Any]], model: str, **_: Any) -> Any:
        response = self._client.messages.create(model=model, max_tokens=16, messages=messages)
        content = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
