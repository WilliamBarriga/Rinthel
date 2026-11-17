"""The daemon and config must agree on the root `.env`, without patching
loose paths, which is exactly what hid a bug (the daemon computed
`parent.parent` = `rinthel/` while config looked for `.git` in another root)."""

from rinthel_tui.config import default_config


def test_post_config_lands_where_config_reads(client, service_headers, daemon_cfg, monkeypatch):
    monkeypatch.delenv("RINTHEL_TEMPERATURE", raising=False)

    response = client.post("/config", json={"overrides": {"RINTHEL_TEMPERATURE": "0.42"}}, headers=service_headers)

    assert response.json()["ok"] is True
    assert default_config(daemon_cfg.instance, platform=daemon_cfg.platform).llama.temperature == 0.42
