"""Fixtures compartidas. Todo test acá corre sin tocar red/subprocess real:
mockeamos create_subprocess_exec/_port_in_use/_http_ok a nivel de cada test,
no acá, para que quede explícito qué se está simulando en cada caso."""

import dataclasses

import pytest

from rinthel_tui.config import default_config


class FakeReport:
    """PhaseReport de prueba: junta los mensajes en listas en vez de imprimir,
    para poder assertear contra ellos."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def success(self, msg: str) -> None:
        self.successes.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)


@pytest.fixture
def report() -> FakeReport:
    return FakeReport()


@pytest.fixture
def cfg(tmp_path):
    """RinthelConfig real (misma construcción que en prod vía default_config())
    con los paths de log redirigidos a tmp_path para no tocar el filesystem
    real del repo. RinthelConfig es composición de sub-configs congelados
    (cfg.llama, cfg.whisper, cfg.tts, ...), así que hay que reemplazar cada
    sub-config con dataclasses.replace, no el campo directamente."""
    base = default_config()
    return dataclasses.replace(
        base,
        llama=dataclasses.replace(base.llama, log=tmp_path / "llama-server.log"),
        whisper=dataclasses.replace(base.whisper, log=tmp_path / "whisper-server.log"),
        tts=dataclasses.replace(base.tts, log=tmp_path / "tts-piper.log"),
    )
