"""Focused contract test for the dependency-free MemoryCD AutoMem adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch


HARNESS = Path(mkdtemp(prefix="memorycd-test-harness-"))
HARNESS.mkdir(parents=True, exist_ok=True)
(HARNESS / "methods").mkdir(exist_ok=True)
(HARNESS / "methods" / "__init__.py").touch()
(HARNESS / "methods" / "base_method.py").write_text(
    "class BaseMethod:\n    def __init__(self, max_memory_items=None, **kwargs): self.max_memory_items=max_memory_items\n",
    encoding="utf-8",
)
SOURCE = Path(__file__).with_name("automem_method.py")
(HARNESS / "methods" / "automem.py").write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
sys.path.insert(0, str(HARNESS))

from methods.automem import AutoMemMethod  # noqa: E402


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.value).encode()


def test_ingest_links_and_relation_expanded_recall():
    calls = []
    ids = iter(["domain-books", "book-1", "domain-electronics", "electronic-1"])

    def fake_open(request, timeout):
        calls.append((request.method, request.full_url, json.loads(request.data or b"{}")))
        if request.full_url.endswith("/memory"):
            return FakeResponse({"id": next(ids)})
        if request.full_url.startswith("http://automem.test/recall"):
            return FakeResponse({"results": [{"id": "book-1"}]})
        return FakeResponse({"status": "success"})

    memory = [
        {"domain_category": "Books", "parent_asin": "book", "title": "Book", "text": "Loved it", "rating": 5},
        {"domain_category": "Electronics", "parent_asin": "phone", "title": "Phone", "text": "Easy", "rating": 5},
    ]
    with patch("methods.automem.urlopen", fake_open):
        method = AutoMemMethod(api_url="http://automem.test", api_token="test", dataset_name="cross_Books", max_memory_items=1, run_id="memorycd-test")
        selected = method.select_memory(memory, {"title": "New book"}, "rating_prediction", user_id="user-1")

    assert selected == [memory[0]]
    associations = [body for method, url, body in calls if url.endswith("/associate")]
    edges = [edge for body in associations for edge in body["associations"]]
    assert {edge["type"] for edge in edges} == {"PART_OF", "RELATES_TO"}
    recall_urls = [url for method, url, _ in calls if "/recall?" in url]
    assert len(recall_urls) == 1 and "expand_relations=true" in recall_urls[0]


if __name__ == "__main__":
    test_ingest_links_and_relation_expanded_recall()
    print("AutoMemMethod contract test passed")
