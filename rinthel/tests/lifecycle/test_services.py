from types import SimpleNamespace

import pytest

from rinthel_tui.lifecycle import services


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize("service,config_attr", [
    (services.PITHAGORAS_SERVICE, "pithagoras"),
    (services.UNDERSTORY_SERVICE, "understory"),
])
def test_compose_uses_the_stack_prepared_for_each_platform(monkeypatch, cfg, platform, service, config_attr):
    monkeypatch.setattr(services, "os", SimpleNamespace(name=platform))
    expected = getattr(cfg, config_attr).dir if platform == "nt" else services.REPO_ROOT
    assert service.dir_of(cfg) == expected
