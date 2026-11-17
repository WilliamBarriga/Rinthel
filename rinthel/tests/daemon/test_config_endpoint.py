"""GET/POST /config — ver docs/adr/0001. El daemon es dueño de toda la
config; estos tests cubren el shape genérico de
`config_edits.config_payload` y el ciclo validar-antes-de-escribir de
`POST /config` por HTTP, sin tocar el `.env` real del repo (el `cfg` del
harness vive sobre una Instance en `tmp_path`)."""

import pytest


@pytest.fixture
def get_config(client, service_headers):
    return lambda: client.get("/config", headers=service_headers).json()


@pytest.fixture
def post_config(client, service_headers):
    return lambda overrides: client.post("/config", json={"overrides": overrides}, headers=service_headers).json()


def _llama_fields(body: dict) -> dict:
    return {f["attr"]: f for f in next(s for s in body["services"] if s["attr"] == "llama")["fields"]}


def test_get_config_lists_every_sub_config_including_install(get_config):
    attrs = [s["attr"] for s in get_config()["services"]]
    assert attrs == ["llama", "moe", "understory", "pithagoras", "install"]


def test_get_config_never_shows_the_instance_secrets(get_config, daemon_cfg):
    body = str(get_config())
    assert daemon_cfg.secrets.service not in body
    assert daemon_cfg.secrets.panel not in body


def test_get_config_excludes_enabled_from_fields_but_surfaces_it_at_top_level(get_config):
    understory = next(s for s in get_config()["services"] if s["attr"] == "understory")
    assert understory["enabled"] is True
    assert understory["enabled_env"] == "RINTHEL_UNDERSTORY_ENABLED"
    assert "enabled" not in [f["attr"] for f in understory["fields"]]


def test_llama_server_has_its_own_toggle(get_config):
    llama = next(s for s in get_config()["services"] if s["attr"] == "llama")
    assert (llama["enabled"], llama["enabled_env"]) == (True, "RINTHEL_LLAMA_ENABLED")


def test_get_config_enabled_is_none_for_sub_configs_without_that_field(get_config):
    services = {s["attr"]: s for s in get_config()["services"]}
    assert services["install"]["enabled"] is None
    assert services["install"]["enabled_env"] is None


def test_get_config_field_carries_kind_group_and_stringified_value(get_config):
    llama_fields = _llama_fields(get_config())
    assert llama_fields["port"]["kind"] == "int"
    assert llama_fields["port"]["value"] == "8080"
    assert llama_fields["temperature"]["group"] == "sampling"
    assert llama_fields["fit_to_memory"]["kind"] == "bool"


def test_post_config_writes_nothing_and_reports_zero_when_no_real_change(post_config, daemon_cfg):
    body = post_config({"RINTHEL_LLAMA_PORT": str(daemon_cfg.llama.port)})
    assert body == {"ok": True, "written": 0, "warnings": []}
    assert not daemon_cfg.instance.env_path.exists()


def test_post_config_writes_the_env_file_on_a_real_change(post_config, daemon_cfg):
    body = post_config({"RINTHEL_TEMPERATURE": "0.42"})
    assert body["ok"] is True
    assert body["written"] == 1
    assert "RINTHEL_TEMPERATURE=0.42" in daemon_cfg.instance.env_path.read_text()


def test_post_config_rejects_a_port_collision_without_writing(post_config, daemon_cfg):
    body = post_config({"RINTHEL_UNDERSTORY_PORT": str(daemon_cfg.llama.port)})
    assert body["ok"] is False
    assert any("choca con" in e for e in body["errors"])
    assert not daemon_cfg.instance.env_path.exists()


def test_post_config_rejects_a_non_positive_numeric_field(post_config):
    body = post_config({"RINTHEL_THREADS": "0"})
    assert body["ok"] is False
    assert any("llama.threads" in e for e in body["errors"])


# ── cfg en memoria se actualiza tras un write propio ────────────────────
# Sin esto, un GET inmediato después de guardar sigue mostrando el valor
# viejo, y "revertir" un campo a su valor original vía la UI no escribe
# nada — se compara contra el mismo valor viejo de `cfg`, así que
# `diff_overrides` lo ve como "sin cambios" (ej.: guardar cache_reuse=300 y
# después intentar volver a 256 deja el .env en 300 silenciosamente).


def test_post_config_applied_is_seen_by_the_next_request(get_config, post_config):
    post_config({"RINTHEL_TEMPERATURE": "0.42"})
    assert _llama_fields(get_config())["temperature"]["value"] == "0.42"


def test_post_config_allows_reverting_to_the_original_value_after_a_save(post_config, daemon_cfg):
    original = str(daemon_cfg.llama.cache_reuse)
    post_config({"RINTHEL_CACHE_REUSE": "300"})

    body = post_config({"RINTHEL_CACHE_REUSE": original})

    assert (body["ok"], body["written"]) == (True, 1)
    assert f"RINTHEL_CACHE_REUSE={original}" in daemon_cfg.instance.env_path.read_text()


@pytest.mark.parametrize("body", [{"overrides": "RINTHEL_THREADS=4"}, {"overrides": {"RINTHEL_THREADS": 4}}, [1]])
def test_post_config_rejects_a_malformed_body_with_422(client, service_headers, body, daemon_cfg):
    response = client.post("/config", json=body, headers=service_headers)
    assert response.status_code == 422
    assert not daemon_cfg.instance.env_path.exists()


def test_configuration_validation_does_not_probe_gpu_or_run_install(post_config, adapters):
    host = adapters.lifecycle_host

    body = post_config({"RINTHEL_TEMPERATURE": "0.42"})

    assert body["ok"] is True
    assert host.host_info.log == []
    assert host.runner.calls == []
    assert host.compose.calls == []


# ── El interruptor único de MTP llega al cliente con sus warnings ─────────


def test_post_config_toggles_mtp_with_a_single_parameter(post_config, get_config, daemon_cfg):
    # Un solo override prende MTP — es el mismo parámetro que el checkbox de
    # [N] CONFIGURAR manda, no hace falta tocar spec_type a mano.
    body = post_config({"RINTHEL_MTP_ENABLED": "true"})

    assert (body["ok"], body["written"]) == (True, 1)
    assert "RINTHEL_MTP_ENABLED=true" in daemon_cfg.instance.env_path.read_text()
    assert _llama_fields(get_config())["mtp_enabled"] == {
        "attr": "mtp_enabled",
        "env": "RINTHEL_MTP_ENABLED",
        "kind": "bool",
        "group": "speculative",
        "value": "true",
    }


def test_post_config_surfaces_the_mtp_batch_warning(post_config):
    # Encender MTP con batch 2048 devuelve el warning en la respuesta: es lo
    # único que la TUI pinta en la barra de estado de [N] CONFIGURAR.
    post_config({"RINTHEL_BATCH_SIZE": "2048", "RINTHEL_UBATCH_SIZE": "2048"})

    body = post_config({"RINTHEL_MTP_ENABLED": "true"})

    assert body["ok"] is True
    assert any("MTP + batch/ubatch" in w for w in body["warnings"])
