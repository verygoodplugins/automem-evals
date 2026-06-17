from runners.matrix.orchestrator import run_matrix


def test_run_matrix_scores_resumes_and_picks_winner(tmp_path):
    configs = [
        {"name": "baseline", "config": {"SEARCH_WEIGHT_VECTOR": "0.35"}},
        {"name": "simpler", "config": {"SEARCH_WEIGHT_VECTOR": "0.35"}},
    ]
    scores = {
        "baseline": {
            "ndcg_10": 0.80,
            "distractor_rate_10": 0.10,
            "latency_ms": 100.0,
            "complexity": 5,
        },
        "simpler": {
            "ndcg_10": 0.801,
            "distractor_rate_10": 0.10,
            "latency_ms": 90.0,
            "complexity": 3,
        },
    }
    provisioned, torn = [], []

    def provision(name, config):
        provisioned.append(name)
        return f"http://stack/{name}"

    def score(api_url, name, config):
        return scores[name]

    def teardown(name):
        torn.append(name)

    out = run_matrix(
        configs,
        results_dir=str(tmp_path),
        automem_commit="abc",
        snapshot_id="snap",
        seed=42,
        baseline_name="baseline",
        provision=provision,
        score=score,
        teardown=teardown,
    )
    assert out["winner"]["name"] == "simpler"  # within ndcg tol, fewer knobs + faster
    assert set(torn) == {"baseline", "simpler"}  # always torn down

    # Resume: second run scores nothing (all cached) but still picks winner.
    provisioned.clear()
    out2 = run_matrix(
        configs,
        results_dir=str(tmp_path),
        automem_commit="abc",
        snapshot_id="snap",
        seed=42,
        baseline_name="baseline",
        provision=provision,
        score=score,
        teardown=teardown,
    )
    assert provisioned == []  # nothing re-provisioned
    assert out2["winner"]["name"] == "simpler"


def test_run_matrix_tears_down_on_score_failure(tmp_path):
    torn = []

    def provision(name, config):
        return "http://x"

    def score(api_url, name, config):
        raise RuntimeError("boom")

    def teardown(name):
        torn.append(name)

    out = run_matrix(
        [{"name": "baseline", "config": {}}],
        results_dir=str(tmp_path),
        automem_commit="abc",
        snapshot_id="snap",
        seed=1,
        baseline_name="baseline",
        provision=provision,
        score=score,
        teardown=teardown,
    )
    assert torn == ["baseline"]  # finally ran despite the failure
    assert out["rows"][0].status == "error"
