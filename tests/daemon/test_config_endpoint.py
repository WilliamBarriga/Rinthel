"""GET/POST /config — ver docs/adr/0001. El daemon es dueño de toda la
config; estos tests cubren el shape genérico de
`config_routes.config_payload` y el ciclo validar-antes-de-escribir de
`POST /config` a través de las rutas de `daemon.py`, sin tocar el `.env`
real del repo (`_ENV_PATH`/`_ENV_EXAMPLE_PATH` se monkeypatchean a rutas de
`tmp_path`)."""

import json

import pytest

from rinthel_tui import daemon


@pytest.fixture(autouse=True)
def _isolated_env_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(daemon, "_ENV_EXAMPLE_PATH", tmp_path / ".env.example")
    # `post_config` reasigna `daemon.cfg` en memoria tras un write exitoso —
    # sin este snapshot/restore, un test que guarda algo dejaría `daemon.cfg`
    # mutado para el resto de la sesión de pytest (es un global de módulo,
    # no algo por-test).
    monkeypatch.setattr(daemon, "cfg", daemon.cfg)


def test_get_config_lists_every_sub_config_including_install():
    body = json.loads(daemon.get_config().body)
    attrs = [s["attr"] for s in body["services"]]
    assert attrs == ["llama", "moe", "understory", "pithagoras", "install"]


def test_get_config_excludes_enabled_from_fields_but_surfaces_it_at_top_level():
    body = json.loads(daemon.get_config().body)
    llama = next(s for s in body["services"] if s["attr"] == "llama")
    assert llama["enabled"] is True
    assert llama["enabled_env"] == "RINTHEL_LLAMA_ENABLED"
    assert "enabled" not in [f["attr"] for f in llama["fields"]]


def test_get_config_enabled_is_none_for_sub_configs_without_that_field():
    body = json.loads(daemon.get_config().body)
    moe = next(s for s in body["services"] if s["attr"] == "moe")
    install = next(s for s in body["services"] if s["attr"] == "install")
    assert moe["enabled"] is None
    assert moe["enabled_env"] is None
    assert install["enabled"] is None
    assert install["enabled_env"] is None


def test_get_config_field_carries_kind_group_and_stringified_value():
    body = json.loads(daemon.get_config().body)
    llama_fields = {f["attr"]: f for f in next(s for s in body["services"] if s["attr"] == "llama")["fields"]}
    assert llama_fields["port"]["kind"] == "int"
    assert llama_fields["port"]["value"] == "8080"
    assert llama_fields["temperature"]["group"] == "sampling"
    assert llama_fields["fit_to_memory"]["kind"] == "bool"


async def test_post_config_writes_nothing_and_reports_zero_when_no_real_change():
    response = await daemon.post_config({"overrides": {"RINTHEL_LLAMA_PORT": str(daemon.cfg.llama.port)}})
    body = json.loads(response.body)
    assert body == {"ok": True, "written": 0, "warnings": []}
    assert not daemon._ENV_PATH.exists()


async def test_post_config_writes_the_env_file_on_a_real_change():
    response = await daemon.post_config({"overrides": {"RINTHEL_TEMPERATURE": "0.42"}})
    body = json.loads(response.body)
    assert body["ok"] is True
    assert body["written"] == 1
    assert "RINTHEL_TEMPERATURE=0.42" in daemon._ENV_PATH.read_text()


async def test_post_config_rejects_a_port_collision_without_writing():
    response = await daemon.post_config({"overrides": {"RINTHEL_UNDERSTORY_PORT": str(daemon.cfg.llama.port)}})
    body = json.loads(response.body)
    assert body["ok"] is False
    assert any("choca con" in e for e in body["errors"])
    assert not daemon._ENV_PATH.exists()


async def test_post_config_rejects_a_non_positive_numeric_field():
    response = await daemon.post_config({"overrides": {"RINTHEL_THREADS": "0"}})
    body = json.loads(response.body)
    assert body["ok"] is False
    assert any("llama.threads" in e for e in body["errors"])


# ── cfg en memoria se actualiza tras un write propio ────────────────────
# Sin esto, un GET inmediato después de guardar sigue mostrando el valor
# viejo, y "revertir" un campo a su valor original vía la UI no escribe
# nada — se compara contra el mismo valor viejo de `cfg`, así que
# `diff_overrides` lo ve como "sin cambios" (ej.: guardar cache_reuse=300 y
# después intentar volver a 256 deja el .env en 300 silenciosamente).


async def test_post_config_updates_cfg_in_memory_so_get_reflects_the_new_value():
    original_temp = daemon.cfg.llama.temperature
    await daemon.post_config({"overrides": {"RINTHEL_TEMPERATURE": "0.42"}})
    assert daemon.cfg.llama.temperature == 0.42
    assert daemon.cfg.llama.temperature != original_temp

    body = json.loads(daemon.get_config().body)
    llama_fields = {f["attr"]: f for f in next(s for s in body["services"] if s["attr"] == "llama")["fields"]}
    assert llama_fields["temperature"]["value"] == "0.42"


async def test_post_config_allows_reverting_to_the_original_value_after_a_save():
    original = str(daemon.cfg.llama.cache_reuse)
    await daemon.post_config({"overrides": {"RINTHEL_CACHE_REUSE": "300"}})

    revert = await daemon.post_config({"overrides": {"RINTHEL_CACHE_REUSE": original}})
    body = json.loads(revert.body)

    assert body == {"ok": True, "written": 1, "warnings": []}
    assert f"RINTHEL_CACHE_REUSE={original}" in daemon._ENV_PATH.read_text()
