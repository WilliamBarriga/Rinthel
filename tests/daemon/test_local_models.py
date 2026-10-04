import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from rinthel_tui.config import default_config
from rinthel_tui.local_models import create_router, managed


@pytest.fixture(autouse=True)
def pi_provider(tmp_path):
    path = tmp_path / 'data/pithagoras/home/.pi/agent/models.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'providers': {
        'local-llm': {'baseUrl': 'http://127.0.0.1:8080/v1', 'models': []},
        'other': {'apiKey': 'keep'},
    }}))


def test_local_picker_auth_validation_and_commit(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTAL_SECRET', 'test-secret')
    model = tmp_path / 'new.gguf'; model.write_bytes(b'GGUF')
    (tmp_path / 'model-profiles.local.json').write_text(json.dumps({'qwen3.6': {'RINTHEL_LLAMA_MODEL_PATH': str(model), 'RINTHEL_MODEL_MIN_BYTES': '4'}}))
    cfg = default_config()
    state = [replace(cfg, llama=replace(cfg.llama, model=tmp_path/'old.gguf'))]
    calls=[]
    async def kill(*args, **kwargs): calls.append('kill')
    async def spawn(*args, **kwargs): calls.append('spawn')
    async def ready(*args, **kwargs): return True
    monkeypatch.setattr(managed,'phase_kill',kill); monkeypatch.setattr(managed,'phase_spawn',spawn); monkeypatch.setattr(managed,'check_ready',ready)
    app=FastAPI(); app.include_router(create_router(tmp_path,lambda:state[0],lambda value:state.__setitem__(0,value)))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.get('/local-models')).status_code == 401
            headers={'x-rinthel-portal':'test-secret'}
            assert (await client.post('/local-models',headers=headers,json={'key':'unknown'})).status_code == 400
            assert calls == []
            model.write_bytes(b'')
            assert (await client.post('/local-models',headers=headers,json={'key':'qwen3.6'})).status_code == 400
            assert calls == []
            model.write_bytes(b'GGUF')
            response=await client.post('/local-models',headers=headers,json={'key':'qwen3.6'})
            assert response.status_code == 200
            assert response.json()['active'] == 'qwen3.6'
            assert state[0].llama.model == model
            assert str(model) in (tmp_path/'.env').read_text()
            provider = json.loads((tmp_path/'data/pithagoras/home/.pi/agent/models.json').read_text())
            assert provider['providers']['other']['apiKey'] == 'keep'
            assert provider['providers']['local-llm']['models'][0]['id'] == str(model)
    asyncio.run(run())


def test_failed_switch_restores_previous_config(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTAL_SECRET', 'test-secret')
    model=tmp_path/'bad.gguf';model.write_bytes(b'GGUF')
    (tmp_path/'model-profiles.local.json').write_text(json.dumps({'bad':{'RINTHEL_LLAMA_MODEL_PATH':str(model)}}))
    state=[default_config()];old=state[0];started=[]
    provider = tmp_path/'data/pithagoras/home/.pi/agent/models.json'
    provider_before = provider.read_bytes()
    async def kill(*args,**kwargs): pass
    async def spawn(cfg,*args,**kwargs):
        started.append(cfg.llama.model)
        if cfg.llama.model == model: raise RuntimeError('invalid model')
    async def ready(*args,**kwargs): return True
    monkeypatch.setattr(managed,'phase_kill',kill);monkeypatch.setattr(managed,'phase_spawn',spawn);monkeypatch.setattr(managed,'check_ready',ready)
    app=FastAPI();app.include_router(create_router(tmp_path,lambda:state[0],lambda value:state.__setitem__(0,value)))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.post('/local-models',headers={'x-rinthel-portal':'test-secret'},json={'key':'bad'})
            assert response.status_code == 500
            assert state[0] == old
            assert started == [model,old.llama.model]
            assert not (tmp_path/'.env').exists()
            assert provider.read_bytes() == provider_before
    asyncio.run(run())


def test_malformed_request_and_catalogue_do_not_start_model(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTAL_SECRET', 'test-secret')
    app = FastAPI()
    app.include_router(create_router(tmp_path, default_config, lambda cfg: None))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            headers = {'x-rinthel-portal': 'test-secret'}
            assert (await client.post('/local-models', headers=headers, content='{broken')).status_code == 400
            (tmp_path/'model-profiles.local.json').write_text('[]')
            assert (await client.get('/local-models', headers=headers)).status_code == 400
    asyncio.run(run())


def test_busy_switch_rejects_second_request(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTAL_SECRET', 'test-secret')
    router = create_router(tmp_path, default_config, lambda cfg: None)
    app = FastAPI()
    app.include_router(router)
    async def run():
        async with router.model_lock:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/local-models', headers={'x-rinthel-portal': 'test-secret'}, json={'key': 'x'})
                assert response.status_code == 409
    asyncio.run(run())


def test_changed_inference_settings_reload_same_model(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTAL_SECRET', 'test-secret')
    model = tmp_path/'model with # and $ signs.gguf'
    model.write_bytes(b'GGUF')
    (tmp_path/'model-profiles.local.json').write_text(json.dumps({'local': {
        'RINTHEL_LLAMA_MODEL_PATH': str(model), 'RINTHEL_CONTEXT_WINDOW': '32768',
    }}))
    base = default_config()
    state = [replace(base, llama=replace(base.llama, model=model, context_window=65536))]
    calls = []
    async def kill(*args, **kwargs): calls.append('kill')
    async def spawn(*args, **kwargs): calls.append('spawn')
    async def ready(*args, **kwargs): return True
    monkeypatch.setattr(managed, 'phase_kill', kill)
    monkeypatch.setattr(managed, 'phase_spawn', spawn)
    monkeypatch.setattr(managed, 'check_ready', ready)
    app = FastAPI()
    app.include_router(create_router(tmp_path, lambda: state[0], lambda value: state.__setitem__(0, value)))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/local-models', headers={'x-rinthel-portal': 'test-secret'}, json={'key': 'local'})
            assert response.status_code == 200
    asyncio.run(run())
    from dotenv import dotenv_values
    assert dotenv_values(tmp_path/'.env')['RINTHEL_LLAMA_MODEL_PATH'] == str(model)
    assert state[0].llama.context_window == 32768
    assert calls == ['kill', 'spawn']
