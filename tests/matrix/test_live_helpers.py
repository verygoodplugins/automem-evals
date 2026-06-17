from runners.matrix.live import compose_up_cmd, compose_down_cmd


def test_compose_up_cmd_uses_project_and_both_files():
    ports = {"api": 18001, "falkor": 18002, "falkor_ui": 18003, "qdrant": 18004}
    cmd = compose_up_cmd("automem_eval_baseline", "/repo/automem", "/tmp/ov.yml", ports)
    assert cmd[:2] == ["docker", "compose"]
    assert "-p" in cmd and "automem_eval_baseline" in cmd
    assert "/repo/automem/docker-compose.yml" in cmd
    assert "/tmp/ov.yml" in cmd
    assert cmd[-2:] == ["up", "-d"]


def test_compose_down_cmd_removes_volumes():
    cmd = compose_down_cmd("automem_eval_baseline")
    assert "down" in cmd and "-v" in cmd and "--remove-orphans" in cmd
    assert "automem_eval_baseline" in cmd
