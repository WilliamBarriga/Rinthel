import dataclasses

import pytest

from rinthel_tui.lifecycle.services import LLAMA_SERVICE, UNDERSTORY_SERVICE
from rinthel_tui.tui.widgets.service_badge import ServiceBadge


def test_for_service_local_process_uses_display_name_and_ready_url(cfg):
    badge = ServiceBadge.for_service(LLAMA_SERVICE, cfg)
    assert badge.label_text == "llama-server"
    assert badge.url == f"http://127.0.0.1:{cfg.llama.port}/v1/models"


def test_for_service_label_override(cfg):
    badge = ServiceBadge.for_service(LLAMA_SERVICE, cfg, label="LLAMA")
    assert badge.label_text == "LLAMA"


def test_for_service_docker_compose_uses_ready_url_of(cfg):
    badge = ServiceBadge.for_service(UNDERSTORY_SERVICE, cfg)
    assert badge.label_text == "Understory"
    assert badge.url == f"http://127.0.0.1:{cfg.understory.port}/"


def test_for_service_raises_without_ready_url_of(cfg):
    service_without_ready_url = dataclasses.replace(UNDERSTORY_SERVICE, ready_url_of=None)
    with pytest.raises(ValueError, match="ready_url_of"):
        ServiceBadge.for_service(service_without_ready_url, cfg)
