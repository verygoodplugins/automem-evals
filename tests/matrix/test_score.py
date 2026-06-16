from runners.matrix.score import score_stack


def make_fake_recall(mapping):
    """mapping: query -> list of result ids."""

    def _recall(api_url, headers, query, **kwargs):
        return {"results": [{"memory": {"id": i}} for i in mapping[query]]}

    return _recall


def test_score_stack_computes_scorecard_axes():
    queries = [
        {"query": "q1", "expected_ids": ["a"], "category": "Decision"},
        {"query": "q2", "expected_ids": ["b"], "category": "Decision"},
    ]
    fake = make_fake_recall({"q1": ["a", "d1"], "q2": ["x", "b"]})
    config = {"SEARCH_WEIGHT_VECTOR": "0.35", "SEARCH_WEIGHT_KEYWORD": "0.0"}
    card = score_stack(
        "http://x",
        {},
        queries,
        distractor_ids={"d1"},
        config=config,
        recall_fn=fake,
    )
    # q1: a at rank1 -> ndcg 1.0 ; q2: b at rank2 -> ndcg ~0.63
    assert 0.7 < card["ndcg_10"] < 0.85
    # q1 has 1 distractor in top10 of 2 results = 0.5 ; q2 has 0 -> mean 0.25
    assert card["distractor_rate_10"] == 0.25
    assert card["complexity"] == 1  # only one nonzero weight
    assert "latency_ms" in card
