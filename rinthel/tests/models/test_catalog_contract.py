"""Suite de contrato del puerto ``Catalog``: el archivo ``models.local.json``
(``JsonCatalog``) y el doble en memoria. Después, la validación al leer, que
es solo del archivo: una entrada inválida queda listada como no activable y
el catálogo no falla."""

import json
from pathlib import Path

import pytest

from rinthel_tui.models.adapters.json_catalog import JsonCatalog
from rinthel_tui.models.adapters.memory import InMemoryCatalog
from rinthel_tui.models.domain.errors import CatalogUnavailable
from rinthel_tui.models.domain.types import CatalogEntry, LocalModel


def gguf(path: Path, header: bytes = b"GGUF") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"\0" * 32)
    return path


def entry(model_id: str, gguf_path: Path, **extra) -> dict:
    return {
        "id": model_id, "name": model_id.upper(), "capability": "llm", "gguf": str(gguf_path),
        "context_window": 4096, **extra,
    }


def write_catalog(path: Path, entries: list[dict]) -> Path:
    path.write_text(json.dumps({"models": entries}))
    return path


@pytest.fixture(params=["json", "memory"])
def two_models(request, tmp_path):
    """Un catálogo con ``a`` y ``b`` válidos, en ese orden."""
    a, b = gguf(tmp_path / "a.gguf"), gguf(tmp_path / "b.gguf")
    if request.param == "memory":
        return InMemoryCatalog([
            CatalogEntry("a", LocalModel("a", "A", "llm", a, 4096)),
            CatalogEntry("b", LocalModel("b", "B", "llm", b, 4096)),
        ])
    return JsonCatalog(write_catalog(tmp_path / "models.local.json", [entry("a", a), entry("b", b)]))


def test_entries_keep_the_declared_order(two_models):
    assert [e.id for e in two_models.entries()] == ["a", "b"]


def test_valid_entries_are_activable(two_models):
    assert all(e.activable for e in two_models.entries())


def test_unreadable_catalog_is_unavailable(tmp_path):
    (tmp_path / "models.local.json").write_text("{not json")
    with pytest.raises(CatalogUnavailable):
        JsonCatalog(tmp_path / "models.local.json").entries()
    memory = InMemoryCatalog([])
    memory.fail_next("entries", CatalogUnavailable("caído"))
    with pytest.raises(CatalogUnavailable):
        memory.entries()


# ── validación al leer (solo el archivo) ─────────────────────────────────


def _only(tmp_path, raw: dict) -> CatalogEntry:
    (entry_,) = JsonCatalog(write_catalog(tmp_path / "models.local.json", [raw])).entries()
    return entry_


def test_a_missing_catalog_file_is_an_empty_catalog(tmp_path):
    assert JsonCatalog(tmp_path / "models.local.json").entries() == []


def test_a_valid_entry_reads_every_field(tmp_path):
    model = gguf(tmp_path / "m.gguf")
    mmproj = gguf(tmp_path / "mmproj.gguf")
    read = _only(tmp_path, entry(
        "m", model, mmproj=str(mmproj), mtp=True, reasoning_format="deepseek", overrides={"temperature": 0.6},
    ))
    assert read.activable
    assert read.model == LocalModel(
        "m", "M", "llm", model, 4096, mmproj=mmproj, mtp=True, reasoning_format="deepseek",
        overrides={"temperature": 0.6},
    )


def test_defaults_of_the_optional_fields(tmp_path):
    read = _only(tmp_path, entry("m", gguf(tmp_path / "m.gguf")))
    assert (read.model.mmproj, read.model.mtp, read.model.reasoning_format, read.model.overrides) == (
        None, False, "qwen-chat-template", {},
    )


def test_a_tilde_in_paths_is_the_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    gguf(tmp_path / "models" / "m.gguf")
    read = _only(tmp_path, entry("m", Path("~/models/m.gguf")))
    assert read.activable
    assert read.model.gguf == tmp_path / "models" / "m.gguf"


@pytest.mark.parametrize("problem,make", [
    ("GGUF no encontrado", lambda d: entry("m", d / "nada.gguf")),
    ("cabecera", lambda d: entry("m", gguf(d / "m.gguf", header=b"NOPE"))),
    ("mmproj no encontrado", lambda d: entry("m", gguf(d / "m.gguf"), mmproj=str(d / "nada-mmproj.gguf"))),
])
def test_an_invalid_file_leaves_the_entry_listed_but_not_activable(tmp_path, problem, make):
    read = _only(tmp_path, make(tmp_path))
    assert read.id == "m"
    assert not read.activable
    assert problem in read.problem


@pytest.mark.parametrize("change", [
    {"capability": "vision"},
    {"reasoning_format": "inventado"},
    {"context_window": 0},
    {"overrides": {"n_cpu_moe": 99}},
    {"name": ""},
])
def test_a_malformed_entry_is_not_activable(tmp_path, change):
    read = _only(tmp_path, {**entry("m", gguf(tmp_path / "m.gguf")), **change})
    assert read.id == "m"
    assert not read.activable


def test_an_entry_without_id_is_listed_by_position(tmp_path):
    raw = entry("m", gguf(tmp_path / "m.gguf"))
    del raw["id"]
    read = _only(tmp_path, raw)
    assert read.id == "entrada-1"
    assert not read.activable


def test_a_repeated_id_leaves_the_second_one_not_activable(tmp_path):
    a = gguf(tmp_path / "a.gguf")
    first, second = JsonCatalog(
        write_catalog(tmp_path / "models.local.json", [entry("a", a), entry("a", a)])
    ).entries()
    assert first.activable
    assert not second.activable
    assert "repetido" in second.problem


# ── voice entries (stt/tts) ──────────────────────────────────────────────


def _voice(model_id: str, capability: str, path: Path, **extra) -> dict:
    return {"id": model_id, "name": model_id.upper(), "capability": capability, "gguf": str(path), **extra}


def test_an_stt_entry_takes_a_whisper_ggml_file_without_a_context_window(tmp_path):
    ggml = tmp_path / "ggml-base.bin"
    ggml.write_bytes(b"lmgg" + b"\0" * 32)

    read = _only(tmp_path, _voice("whisper-base", "stt", ggml))

    assert read.activable, read.problem
    assert (read.model.capability, read.model.gguf, read.model.voice) == ("stt", ggml, None)


def test_a_tts_entry_reads_its_fixed_voice(tmp_path):
    wav = tmp_path / "voice.wav"
    wav.write_bytes(b"RIFF")

    read = _only(tmp_path, _voice("pocket", "tts", gguf(tmp_path / "pocket.gguf"), voice=str(wav)))

    assert read.activable, read.problem
    assert read.model.voice == wav


def test_a_tts_voice_that_does_not_exist_is_not_activable(tmp_path):
    read = _only(tmp_path, _voice("pocket", "tts", gguf(tmp_path / "pocket.gguf"), voice=str(tmp_path / "nada.wav")))

    assert not read.activable
    assert "voz no encontrada" in read.problem


@pytest.mark.parametrize("raw", [
    lambda d: {**entry("m", gguf(d / "m.gguf")), "voice": str(d / "m.gguf")},
    lambda d: _voice("w", "stt", gguf(d / "w.bin"), voice=str(d / "w.bin")),
], ids=["llm", "stt"])
def test_only_a_tts_entry_has_a_voice(tmp_path, raw):
    read = _only(tmp_path, raw(tmp_path))

    assert not read.activable
    assert "voice" in read.problem


def test_a_voice_entry_whose_file_is_missing_is_not_activable(tmp_path):
    read = _only(tmp_path, _voice("w", "stt", tmp_path / "nada.bin"))

    assert not read.activable
    assert "no encontrado" in read.problem
