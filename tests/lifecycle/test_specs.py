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
    assert any("UNDERSTORY" in l for l in labels)
    assert any("PITHAGORAS" in l for l in labels)


def test_boot_phases_excludes_disabled_local_service(cfg):
    disabled = _disable(cfg, "understory")
    labels = _labels(specs.boot_phases(disabled))
    assert not any("UNDERSTORY" in l for l in labels)
    # el resto sigue presente — deshabilitar uno no toca a los demás.
    assert any("LLAMA-SERVER" in l for l in labels)
    assert any("PITHAGORAS" in l for l in labels)


def test_boot_phases_excludes_disabled_docker_service(cfg):
    disabled = _disable(cfg, "pithagoras")
    labels = _labels(specs.boot_phases(disabled))
    assert not any("PITHAGORAS" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)


def test_down_phases_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "pithagoras")
    labels = _labels(specs.down_phases(disabled))
    assert not any("PITHAGORAS" in l for l in labels)
    assert any("LLAMA-SERVER" in l for l in labels)
    assert any("UNDERSTORY" in l for l in labels)


# ── boot_units / down_units (daemon FastAPI, ticket 04) ───────────────────
# Vista agrupada por servicio de boot_phases/down_phases — un ServiceOutcome
# por servicio en vez de un resultado por fase (ver docs/adr/0001).


def test_boot_units_groups_two_phases_per_service(cfg):
    units = dict(specs.boot_units(cfg))
    assert set(units) == {"llama-server", "understory", "pithagoras"}
    for service_specs in units.values():
        assert len(service_specs) == 2  # spawn/up + wait, siempre en pares


def test_boot_units_does_not_include_the_docker_check(cfg):
    # phases.phase_check_docker no es de ningún servicio — el caller
    # (daemon.py) lo corre aparte, con su propio ServiceOutcome("docker").
    units = specs.boot_units(cfg)
    all_labels = [s.label for _, unit_specs in units for s in unit_specs]
    assert not any("DOCKER" in l for l in all_labels)


def test_boot_units_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "understory")
    units = dict(specs.boot_units(disabled))
    assert set(units) == {"llama-server", "pithagoras"}


def test_down_units_groups_one_phase_per_service(cfg):
    units = dict(specs.down_units(cfg))
    assert set(units) == {"llama-server", "understory", "pithagoras"}
    for service_specs in units.values():
        assert len(service_specs) == 1


def test_down_units_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "pithagoras")
    units = dict(specs.down_units(disabled))
    assert set(units) == {"llama-server", "understory"}


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
    disabled = _disable(cfg, "understory")
    groups = specs.reload_phases(disabled)
    numbers = _all_numbers(groups)
    total = sum(len(g) for g in groups)
    assert [n for n, _ in numbers] == list(range(1, total + 1))
    assert not any("UNDERSTORY" in s.label for group in groups for s in group)


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


# ── reload_units (daemon FastAPI, sesión 06) ───────────────────────────────
# Vista agrupada por servicio de las 3 tandas de reload_phases — un
# ServiceOutcome por unidad, mismo criterio que boot_units/down_units.


def test_reload_units_shutdown_groups_kill_and_down(cfg):
    shutdown, _boot, _rebuild = specs.reload_units(cfg)
    # "llama-server" aparece 2 veces (kill + wait-port-free, unidades
    # separadas con el mismo nombre de servicio) — no colapsar con dict().
    assert [service for service, _ in shutdown] == [
        "llama-server",
        "understory",
        "pithagoras",
        "llama-server",
    ]
    understory_specs = next(specs_ for service, specs_ in shutdown if service == "understory")
    assert len(understory_specs) == 1  # down, sin wait
    port_wait_specs = shutdown[-1][1]
    assert len(port_wait_specs) == 1
    assert "PUERTO" in port_wait_specs[0].label and "LIBRE" in port_wait_specs[0].label


def test_reload_units_boot_is_local_only_no_docker_check(cfg):
    _shutdown, boot, _rebuild = specs.reload_units(cfg)
    units = dict(boot)
    assert set(units) == {"llama-server"}  # único LOCAL_SERVICES hoy
    assert len(units["llama-server"]) == 2  # spawn + wait
    all_labels = [s.label for _, unit_specs in boot for s in unit_specs]
    assert not any("DOCKER" in l for l in all_labels)  # lo corre daemon.py aparte


def test_reload_units_rebuild_is_docker_only_with_no_cache(cfg):
    _shutdown, _boot, rebuild = specs.reload_units(cfg)
    units = dict(rebuild)
    assert set(units) == {"understory", "pithagoras"}
    for service, unit_specs in rebuild:
        up_spec = unit_specs[0]
        assert up_spec.kwargs["no_cache"] is True


def test_reload_units_excludes_llama_port_wait_when_llama_disabled(cfg):
    disabled = _disable(cfg, "llama")
    shutdown, boot, _rebuild = specs.reload_units(disabled)
    assert dict(shutdown).get("llama-server") is None
    assert dict(boot).get("llama-server") is None


def test_reload_units_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "understory")
    shutdown, _boot, rebuild = specs.reload_units(disabled)
    assert "understory" not in dict(shutdown)
    assert "understory" not in dict(rebuild)
