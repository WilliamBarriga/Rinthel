import json
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from rinthel_tui.install.ubuntu import prepare

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Linux bootstrap')


def test_fresh_install_and_rerun_preserve_state(tmp_path):
    root = tmp_path / 'repo with spaces'
    root.mkdir()
    prepare(root)
    first = dotenv_values(root / '.env')
    assert first['COMPOSE_FILE'] == 'docker-compose.ubuntu.yml'
    assert first['AUTH_TOKEN'] == first['UNDERSTORY_TOKEN']
    assert first['PUID'] == str(os.getuid())
    assert Path(first['WORKSPACES_DIR']).is_dir()
    assert (root / '.env').stat().st_mode & 0o777 == 0o600
    agent = root / 'data/pithagoras/home/.pi/agent/models.json'
    models = json.loads(agent.read_text())
    models['providers']['other'] = {'apiKey': 'keep'}
    agent.write_text(json.dumps(models))
    memory = root / 'data/understory/agents/index.md'
    memory.write_text('User memory')
    prepare(root)
    assert dotenv_values(root / '.env') == first
    assert memory.read_text() == 'User memory'
    result = json.loads(agent.read_text())['providers']
    assert result['other']['apiKey'] == 'keep'
    assert result['local-llm']['baseUrl'] == 'http://127.0.0.1:8080/v1'
    assert result['local-llm']['models'][0]['id'] == first['RINTHEL_LLAMA_MODEL_PATH']


def test_existing_secrets_ports_and_model_preserved(tmp_path):
    (tmp_path / '.env').write_text('AUTH_TOKEN=keep\nPORTAL_PASSWORD=secret\nRINTHEL_LLAMA_PORT=9090\nRINTHEL_LLAMA_MODEL_PATH=/models/custom.gguf\nRINTHEL_CONTEXT_WINDOW=16384\n')
    prepare(tmp_path)
    values = dotenv_values(tmp_path / '.env')
    assert values['UNDERSTORY_TOKEN'] == 'keep'
    assert values['PORTAL_PASSWORD'] == 'secret'
    assert values['RINTHEL_CONTEXT_WINDOW'] == '16384'
    provider = json.loads((tmp_path / 'data/pithagoras/home/.pi/agent/models.json').read_text())['providers']['local-llm']
    assert provider['baseUrl'] == 'http://127.0.0.1:9090/v1'
    assert provider['models'][0]['id'] == '/models/custom.gguf'


def test_conflicting_tokens_fail_without_mutation(tmp_path):
    env = tmp_path / '.env'
    original = 'AUTH_TOKEN=one\nUNDERSTORY_TOKEN=two\n'
    env.write_text(original)
    with pytest.raises(ValueError, match='deben coincidir'):
        prepare(tmp_path)
    assert env.read_text() == original


def test_existing_compose_selection_is_not_overwritten(tmp_path):
    env = tmp_path / '.env'
    original = 'COMPOSE_FILE=custom.yml\n'
    env.write_text(original)
    with pytest.raises(RuntimeError, match='COMPOSE_FILE'):
        prepare(tmp_path)
    assert env.read_text() == original
