from runners.matrix.compose_lint import lint_compose

CLEAN = """
services:
  falkordb:
    image: falkordb/falkordb
    ports:
      - "${FALKOR_PORT}:6379"
  flask-api:
    build: .
    ports:
      - "${API_PORT}:8001"
"""

DIRTY = """
services:
  falkordb:
    container_name: falkordb
    ports:
      - "6379:6379"
  flask-api:
    ports:
      - "${API_PORT}:8001"
"""


def test_clean_compose_has_no_errors():
    assert lint_compose(CLEAN) == []


def test_dirty_compose_flags_container_name_and_fixed_port():
    errors = lint_compose(DIRTY)
    assert any("container_name" in e for e in errors)
    assert any("6379:6379" in e for e in errors)
    assert len(errors) == 2
