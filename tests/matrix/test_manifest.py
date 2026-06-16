from runners.matrix import manifest as mf


def test_cell_key_is_stable_and_order_independent():
    a = mf.cell_key({"A": "1", "B": "2"}, "abc123", 42, "snap1")
    b = mf.cell_key({"B": "2", "A": "1"}, "abc123", 42, "snap1")
    assert a == b
    assert a != mf.cell_key({"A": "9", "B": "2"}, "abc123", 42, "snap1")
    assert len(a) == 16


def test_round_trip_and_cache(tmp_path):
    row = mf.ManifestRow(
        name="baseline",
        key="deadbeefdeadbeef",
        config={"SEARCH_WEIGHT_VECTOR": "0.35"},
        automem_commit="abc123",
        seed=42,
        snapshot_id="snap1",
        scorecard={
            "name": "baseline",
            "ndcg_10": 0.8,
            "distractor_rate_10": 0.1,
            "latency_ms": 100.0,
            "complexity": 5,
        },
        status="ok",
    )
    assert mf.is_cached(str(tmp_path), row.key) is False
    mf.save_row(str(tmp_path), row)
    assert mf.is_cached(str(tmp_path), row.key) is True
    rows = mf.load_rows(str(tmp_path))
    assert len(rows) == 1
    assert rows[0].name == "baseline"
    assert rows[0].scorecard["ndcg_10"] == 0.8
