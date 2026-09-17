"""BOOT/DOWN/RELOAD filtrados por ``enabled_of`` (Fase 3 del plan de
servicios configurables) — un servicio con ``enabled=False`` en su
sub-config queda afuera de las 3 secuencias.
"""

import dataclasses
import re

from rinthel_tui.lifecycle import specs


def _disable(cfg, attr):
    sub = getattr(cfg, attr)
    return dataclasses.replace(cfg, **{attr: dataclasses.replace(sub, enabled=False)})


# ── boot_units / down_units ───────────────────────────────────────────────
# Un ServiceOutcome por servicio en vez de un resultado por fase (ver
# docs/adr/0001).


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


# ── reload_units ───────────────────────────────────────────────────────────
# Las 3 tandas de RELOAD (shutdown → boot → rebuild), agrupadas por servicio
# — un ServiceOutcome por unidad, mismo criterio que boot_units/down_units.


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


# ── install_units ──────────────────────────────────────────────────────────
# Vista agrupada por InstallUnit — un ServiceOutcome por unidad instalable
# (mismo criterio que boot_units/reload_units), más PREFLIGHT como su propia
# unidad.


def test_install_units_groups_preflight_and_every_unit_by_default(cfg):
    units = dict(specs.install_units(cfg))
    assert set(units) == {"preflight", "llama.cpp + modelo", "pithagoras", "understory"}


def test_install_units_preflight_is_first_and_a_single_phase(cfg):
    units = specs.install_units(cfg)
    assert units[0][0] == "preflight"
    assert len(units[0][1]) == 1


def test_install_units_llama_groups_all_three_steps(cfg):
    units = dict(specs.install_units(cfg))
    assert len(units["llama.cpp + modelo"]) == 3


def test_install_units_excludes_disabled_service(cfg):
    disabled = _disable(cfg, "understory")
    units = dict(specs.install_units(disabled))
    assert set(units) == {"preflight", "llama.cpp + modelo", "pithagoras"}


def test_install_units_does_not_number_labels(cfg):
    # install_units no numera — el daemon solo necesita qué corrió y si
    # salió bien, no un checklist.
    units = specs.install_units(cfg)
    all_labels = [s.label for _, unit_specs in units for s in unit_specs]
    assert not any(re.search(r"\[\d+/\d+\]", l) for l in all_labels)
