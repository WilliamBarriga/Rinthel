"""BOOT/DOWN/RELOAD filtrados por ``enabled_of`` (Fase 3 del plan de
servicios configurables) — un servicio con ``enabled=False`` en su
sub-config queda afuera de las 3 secuencias, y RELOAD renumera sin saltos.
"""

import dataclasses
import re

from rinthel_tui.lifecycle import specs


def _disable(cfg, attr):
    sub = getattr(cfg, attr)
    return dataclasses.replace(cfg, **{attr: dataclasses.replace(sub, enabled=False)})


def _labels(phase_specs):
    return [s.label for s in phase_specs]


# ── boot_phases / down_phases ────────────────────────────────────────────


def test_boot_phases_includes_all_services_by_default(cfg):
    labels = _labels(specs.boot_phases(cfg))
    assert any("LLAMA-SERVER" in l for l in labels)
    assert any("WHISPER" in l for l in labels)
    assert any("TTS" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)
    assert any("PITHAGORAS" in l for l in labels)


def test_boot_phases_excludes_disabled_local_service(cfg):
    disabled = _disable(cfg, "whisper")
    labels = _labels(specs.boot_phases(disabled))
    assert not any("WHISPER" in l for l in labels)
    # el resto sigue presente — deshabilitar uno no toca a los demás.
    assert any("LLAMA-SERVER" in l for l in labels)
    assert any("TTS" in l for l in labels)


def test_boot_phases_excludes_disabled_docker_service(cfg):
    disabled = _disable(cfg, "pithagoras")
    labels = _labels(specs.boot_phases(disabled))
    assert not any("PITHAGORAS" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)


def test_down_phases_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "tts")
    labels = _labels(specs.down_phases(disabled))
    assert not any("TTS" in l for l in labels)
    assert any("LLAMA-SERVER" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)


# ── reload_phases ─────────────────────────────────────────────────────────


def _all_numbers(groups):
    numbers = []
    for group in groups:
        for spec in group:
            match = re.search(r"\[(\d+)/(\d+)\]", spec.label)
            assert match is not None
            numbers.append((int(match.group(1)), int(match.group(2))))
    return numbers


def test_reload_phases_numbers_are_contiguous_by_default(cfg):
    groups = specs.reload_phases(cfg)
    numbers = _all_numbers(groups)
    total = sum(len(g) for g in groups)
    assert [n for n, _ in numbers] == list(range(1, total + 1))
    assert all(n_total == total for _, n_total in numbers)


def test_reload_phases_renumbers_without_gaps_when_service_disabled(cfg):
    disabled = _disable(cfg, "whisper")
    groups = specs.reload_phases(disabled)
    numbers = _all_numbers(groups)
    total = sum(len(g) for g in groups)
    assert [n for n, _ in numbers] == list(range(1, total + 1))
    assert not any("WHISPER" in s.label for group in groups for s in group)


def test_reload_phases_excludes_llama_port_wait_when_llama_disabled(cfg):
    disabled = _disable(cfg, "llama")
    groups = specs.reload_phases(disabled)
    all_labels = [s.label for group in groups for s in group]
    assert not any("PUERTO" in l and "LIBRE" in l for l in all_labels)
    assert not any("LLAMA-SERVER" in l for l in all_labels)


def test_reload_phases_includes_llama_port_wait_by_default(cfg):
    groups = specs.reload_phases(cfg)
    all_labels = [s.label for group in groups for s in group]
    assert any("PUERTO" in l and "LIBRE" in l for l in all_labels)
