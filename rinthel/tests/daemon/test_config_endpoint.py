"""GET/POST /config — ver docs/adr/0001. El daemon es dueño de toda la
config; estos tests cubren el shape genérico de
`config_edits.config_payload` y el ciclo validar-antes-de-escribir de
`POST /config` por HTTP, sin tocar el `.env` real del repo (el `cfg` del
harness vive sobre una Instance en `tmp_path`)."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from rinthel_tui.api import create_app


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
    assert attrs == ["llama", "moe", "understory", "deck", "install", "whisper", "audiocpp"]


def test_get_config_names_the_voice_services(get_config):
    names = {s["attr"]: s["display_name"] for s in get_config()["services"]}
    assert (names["whisper"], names["audiocpp"]) == ("whisper-server", "audiocpp-server")


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


def test_the_local_model_fields_are_not_in_configurar(get_config):
    # Speculative decoding belongs to the Local model (its overrides), not to the .env.
    assert {"spec_type", "spec_draft_n_max"}.isdisjoint(_llama_fields(get_config()))


def test_a_hardware_field_carries_the_validated_profile_value(get_config):
    fields = _llama_fields(get_config())
    assert (fields["n_cpu_moe"]["value"], fields["n_cpu_moe"]["profile"]) == ("60", "60")
    assert fields["cache_type_k"]["profile"] == "f16"


def test_a_field_outside_the_validated_profile_has_no_profile_value(get_config):
    fields = _llama_fields(get_config())
    assert fields["temperature"]["profile"] is None
    assert fields["port"]["profile"] is None


def test_the_profile_value_is_the_one_of_the_platform(daemon_cfg, adapters, service_headers):
    # The .env keeps the Linux value on a Windows Instance: an override.
    app = create_app(dataclasses.replace(daemon_cfg, platform="windows"), adapters=adapters)
    fields = _llama_fields(TestClient(app).get("/config", headers=service_headers).json())

    assert (fields["n_cpu_moe"]["value"], fields["n_cpu_moe"]["profile"]) == ("60", "34")


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




# ── Lo que es de cada Local model ya no es config del .env ─────────────


def test_local_model_fields_are_not_config_fields(get_config):
    envs = {f["env"] for s in get_config()["services"] for f in s["fields"]}
    for env in ("RINTHEL_LLAMA_MODEL_PATH", "RINTHEL_CONTEXT_WINDOW", "RINTHEL_MTP_ENABLED", "RINTHEL_LLAMA_MMPROJ_PATH"):
        assert env not in envs


def test_post_config_surfaces_the_mtp_batch_warning_of_the_active_model(app, post_config, daemon_cfg):
    # Con un Local model que prende MTP, subir el batch a 2048 devuelve el
    # warning en la respuesta: es lo que la TUI pinta en [N] CONFIGURAR.
    app.state.cfg = dataclasses.replace(daemon_cfg, local_model=dataclasses.replace(daemon_cfg.local_model, mtp=True))

    body = post_config({"RINTHEL_BATCH_SIZE": "2048", "RINTHEL_UBATCH_SIZE": "2048"})

    assert body["ok"] is True
    assert any("MTP + batch/ubatch" in w for w in body["warnings"])
