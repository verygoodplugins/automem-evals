import yaml

from runners.matrix.override import build_override


def test_build_override_bakes_config_into_flask_env():
    ports = {"api": 18011, "falkor": 18012, "falkor_ui": 18013, "qdrant": 18014}
    config = {"SEARCH_WEIGHT_VECTOR": "0.5", "RECALL_RELEVANCE_GATE": 0.2}
    ov = build_override(ports, config)

    env = ov["services"]["flask-api"]["environment"]
    assert env["SEARCH_WEIGHT_VECTOR"] == "0.5"
    assert env["RECALL_RELEVANCE_GATE"] == "0.2"  # stringified

    # host ports mapped from the ports dict; internal ports fixed
    assert f"{ports['api']}:8001" in ov["services"]["flask-api"]["ports"]
    assert f"{ports['falkor']}:6379" in ov["services"]["falkordb"]["ports"]
    assert f"{ports['qdrant']}:6333" in ov["services"]["qdrant"]["ports"]

    # no container_name anywhere
    assert "container_name" not in yaml.dump(ov)
