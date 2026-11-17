"""Suite de contrato del puerto ``ActiveModels``: ``instance.toml``
(``TomlActiveModels``) y el doble en memoria."""

import pytest

from rinthel_tui.models.adapters.memory import InMemoryActiveModels
from rinthel_tui.models.adapters.toml_active import TomlActiveModels


@pytest.fixture(params=["toml", "memory"])
def active(request, tmp_path):
    if request.param == "memory":
        return InMemoryActiveModels()
    return TomlActiveModels(tmp_path / "data" / "instance.toml")


def test_nothing_is_active_at_first(active):
    assert active.get("llm") is None


def test_set_is_read_back_per_capability(active):
    active.set("llm", "qwen")
    active.set("tts", "voz")
    active.set("llm", "otro")
    assert (active.get("llm"), active.get("tts"), active.get("stt")) == ("otro", "voz", None)


# ── el archivo ───────────────────────────────────────────────────────────


def test_the_active_model_lives_in_the_models_table(tmp_path):
    path = tmp_path / "instance.toml"
    TomlActiveModels(path).set("llm", "qwen")
    assert path.read_text() == '\n[models]\nllm = "qwen"\n'


def test_set_keeps_what_others_wrote_in_the_file(tmp_path):
    path = tmp_path / "instance.toml"
    path.write_text('nombre = "casa"\n\n[deck]\ntema = "oscuro"\n\n[models]\ntts = "voz"\n')
    TomlActiveModels(path).set("llm", "qwen")
    reread = TomlActiveModels(path)
    assert (reread.get("llm"), reread.get("tts")) == ("qwen", "voz")
    assert 'nombre = "casa"' in path.read_text()
    assert 'tema = "oscuro"' in path.read_text()


def test_a_non_string_id_is_no_active_model(tmp_path):
    path = tmp_path / "instance.toml"
    path.write_text("[models]\nllm = 3\n")
    assert TomlActiveModels(path).get("llm") is None
