from runners.matrix import resources as r


def test_cell_ports_are_deterministic_and_non_overlapping():
    p0 = r.cell_ports(0)
    p1 = r.cell_ports(1)
    assert p0 == {"api": 18001, "falkor": 18002, "falkor_ui": 18003, "qdrant": 18004}
    assert p1["api"] == 18011
    # no overlap between adjacent cells' blocks
    assert set(p0.values()).isdisjoint(set(p1.values()))


def test_max_concurrency_respects_headroom_and_floor():
    assert r.max_concurrency(80, 5) == 12  # floor(80*0.8/5)=12
    assert r.max_concurrency(4, 5) == 1  # floor=0 -> floored to 1
    assert r.max_concurrency(80, 5, headroom=0.5) == 8
