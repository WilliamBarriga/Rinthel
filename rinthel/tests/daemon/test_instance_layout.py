"""El daemon y config tienen que coincidir en el `.env` raíz — sin
monkeypatch de paths sueltos, que es justo lo que escondía un bug
(daemon calculaba `parent.parent` = `rinthel/`, config buscaba `.git` en
otra raíz)."""

from rinthel_tui.config import default_config


def test_post_config_lands_where_config_reads(client, service_headers, daemon_cfg, monkeypatch):
    monkeypatch.delenv("RINTHEL_TEMPERATURE", raising=False)

    response = client.post("/config", json={"overrides": {"RINTHEL_TEMPERATURE": "0.42"}}, headers=service_headers)

    assert response.json()["ok"] is True
    assert default_config(daemon_cfg.instance).llama.temperature == 0.42
