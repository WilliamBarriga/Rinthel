"""``hostexecd`` as a ``LocalProcessService`` of the daemon: what its spec
hands the ``Processes`` port (argv, environment, log, readiness URL) and how
the Lifecycle plans and the Platform treat it. Pure: no process is started,
only the ``cfg`` of the test and the spec built from it."""

import dataclasses
import sys

from rinthel_tui.config import default_config
from rinthel_tui.instance import Instance
from rinthel_tui.lifecycle import specs
from rinthel_tui.lifecycle.services import DECK_SERVICE, HOSTEXECD_SERVICE


def _with_token(cfg, token="tok"):
    return dataclasses.replace(cfg, hostexecd=dataclasses.replace(cfg.hostexecd, token=token))


def _services(plan):
    return [unit.service for batch in plan.batches for unit in batch.units]


def test_it_runs_the_hostexecd_module_with_the_daemons_python(cfg):
    spec = HOSTEXECD_SERVICE.spec(cfg)

    assert spec.argv == (sys.executable, "-m", "hostexecd.daemon")


def test_its_port_token_and_instance_root_reach_the_process_by_environment(cfg):
    spec = HOSTEXECD_SERVICE.spec(_with_token(cfg, "s3cret"))

    assert spec.port == 8766
    assert spec.env == {
        "RINTHEL_HOSTEXECD_PORT": "8766",
        "RINTHEL_HOSTEXECD_TOKEN": "s3cret",
        "RINTHEL_INSTANCE_ROOT": str(cfg.instance.root),
    }


def test_its_output_goes_to_the_logs_and_readiness_is_a_loopback_health_check(cfg):
    spec = HOSTEXECD_SERVICE.spec(cfg)

    assert spec.log == cfg.instance.logs_dir / "hostexecd.log"
    assert spec.ready_url == "http://127.0.0.1:8766/health"


def test_the_token_comes_from_the_root_env_and_the_port_is_configurable(tmp_path, monkeypatch):
    monkeypatch.delenv("RINTHEL_HOSTEXECD_TOKEN", raising=False)
    monkeypatch.delenv("RINTHEL_HOSTEXECD_PORT", raising=False)
    (tmp_path / ".env").write_text("RINTHEL_HOSTEXECD_TOKEN=from-install\nRINTHEL_HOSTEXECD_PORT=9900\n")

    cfg = default_config(Instance(tmp_path), platform="linux")

    assert cfg.hostexecd.token == "from-install"
    assert cfg.hostexecd.port == 9900


def test_it_is_enabled_on_linux_and_never_on_windows(tmp_path):
    linux = default_config(Instance(tmp_path), platform="linux")
    windows = default_config(Instance(tmp_path), platform="windows")

    assert HOSTEXECD_SERVICE.enabled_of(linux) is True
    assert HOSTEXECD_SERVICE.enabled_of(windows) is False
    forced = dataclasses.replace(windows, hostexecd=dataclasses.replace(windows.hostexecd, enabled=True))
    assert HOSTEXECD_SERVICE.enabled_of(forced) is False


def test_boot_spawns_and_awaits_it_after_llama_and_before_the_docker_services(cfg):
    plan = specs.boot_plan(cfg)
    hostexecd = next(u for b in plan.batches for u in b.units if u.service == "hostexecd")

    assert _services(plan) == ["docker", "llama-server", "hostexecd", "understory", "deck"]
    assert [p.label for p in hostexecd.phases] == ["◈ HOSTEXECD  --  HOST EXEC", "◈ ESPERANDO HOSTEXECD"]


def test_terminate_stops_it_by_its_port(cfg):
    plan = specs.terminate_plan(cfg)
    (unit,) = [u for b in plan.batches for u in b.units if u.service == "hostexecd"]

    assert [p.label for p in unit.phases] == ["◈ HOSTEXECD  --  HOST EXEC"]
    assert unit.phases[0].kwargs["service"].port == 8766


def test_deck_is_handed_its_url_built_with_the_host_address_and_the_token(cfg):
    cfg = _with_token(cfg, "s3cret")
    cfg = dataclasses.replace(cfg, deck=dataclasses.replace(cfg.deck, host_address="10.0.0.5"))

    env = DECK_SERVICE.spec(cfg).stack.env

    assert env["RINTHEL_HOSTEXECD_URL"] == "http://10.0.0.5:8766"
    assert env["RINTHEL_HOSTEXECD_TOKEN"] == "s3cret"


def test_deck_gets_neither_url_nor_token_where_hostexecd_does_not_run(cfg):
    cfg = _with_token(cfg, "s3cret")
    disabled = dataclasses.replace(cfg, hostexecd=dataclasses.replace(cfg.hostexecd, enabled=False))

    for off in (disabled, dataclasses.replace(cfg, platform="windows")):
        env = DECK_SERVICE.spec(off).stack.env
        # Empty, not absent: what the daemon passes wins over the root .env in compose.
        assert env["RINTHEL_HOSTEXECD_URL"] == ""
        assert env["RINTHEL_HOSTEXECD_TOKEN"] == ""


def test_no_plan_touches_it_on_windows(cfg):
    windows = dataclasses.replace(cfg, platform="windows")

    for build in (specs.boot_plan, specs.terminate_plan, specs.reload_plan):
        assert "hostexecd" not in _services(build(windows))
