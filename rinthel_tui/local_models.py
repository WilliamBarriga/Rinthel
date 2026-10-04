"""Authenticated local model switching for the portal (one GPU, one model)."""
import asyncio
import hmac
import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from rinthel_tui.config import ConfigError, LLAMA_FIELDS, MOE_FIELDS, with_overrides
from rinthel_tui.env_file import update_env_file
from rinthel_tui.lifecycle import managed_service as managed
from rinthel_tui.lifecycle.services import LLAMA_SERVICE


class Report:
    def info(self, message): pass
    success = warn = info
    def error(self, message): pass


def load_profiles(root: Path) -> dict[str, dict[str, str]]:
    path = root / 'model-profiles.local.json'
    profiles = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(profiles, dict):
        raise ValueError('El catálogo debe ser un objeto JSON')
    allowed = {field.env for field in (*LLAMA_FIELDS, *MOE_FIELDS)}
    allowed.update({'RINTHEL_MODEL_MIN_BYTES', 'RINTHEL_MODEL_NAME'})
    for key, values in profiles.items():
        if not isinstance(values, dict) or not values.get('RINTHEL_LLAMA_MODEL_PATH'):
            raise ValueError(f'Perfil inválido: {key}')
        if any(name not in allowed or not isinstance(value, str) or '\n' in value or '\r' in value
               for name, value in values.items()):
            raise ValueError(f'Configuración inválida en el perfil {key}')
        if int(values.get('RINTHEL_MODEL_MIN_BYTES', '4')) < 4:
            raise ValueError('RINTHEL_MODEL_MIN_BYTES debe ser al menos 4')
    return profiles


def register_models(root: Path, profiles: dict[str, dict[str, str]]) -> None:
    """Register selectable models without replacing other Pi providers."""
    path = root / 'data/pithagoras/home/.pi/agent/models.json'
    config = json.loads(path.read_text())
    provider = config['providers']['local-llm']
    provider['models'] = [
        {'id': values['RINTHEL_LLAMA_MODEL_PATH'], 'name': values.get('RINTHEL_MODEL_NAME', key)}
        for key, values in profiles.items()
    ]
    path.write_text(json.dumps(config, indent=2) + '\n')


def model_env_overrides(values: dict[str, str]) -> dict[str, str]:
    return {name: "'" + value.replace("'", "\\'") + "'"
            for name, value in values.items()
            if name not in {'RINTHEL_MODEL_MIN_BYTES', 'RINTHEL_MODEL_NAME'}}


def create_router(root: Path, get_config, set_config):
    router = APIRouter()
    lock = asyncio.Lock()

    def profiles():
        return load_profiles(root)

    def authorized(request):
        secret = os.environ.get('PORTAL_SECRET', '')
        return bool(secret) and hmac.compare_digest(request.headers.get('x-rinthel-portal', ''), secret)

    def catalogue(available=None, cfg=None):
        cfg = get_config() if cfg is None else cfg
        available = profiles() if available is None else available
        return {'active': next((k for k,v in available.items() if Path(v['RINTHEL_LLAMA_MODEL_PATH']).expanduser() == cfg.llama.model), None),
                'models': [{'key': k, 'name': v.get('RINTHEL_MODEL_NAME', k),
                            'id': v['RINTHEL_LLAMA_MODEL_PATH'], 'available': Path(v['RINTHEL_LLAMA_MODEL_PATH']).expanduser().is_file()}
                           for k,v in available.items()], 'busy': lock.locked()}

    async def launch(cfg):
        await managed.phase_spawn(cfg, Report(), service=LLAMA_SERVICE)
        for _ in range(180):
            if await managed.check_ready(cfg, LLAMA_SERVICE): return
            await asyncio.sleep(1)
        raise RuntimeError('El modelo no respondió a tiempo. Revisa logs/llama-server.log.')

    @router.get('/local-models')
    async def listing(request: Request):
        if not authorized(request): return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        try:
            return catalogue()
        except (ValueError, OSError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)

    @router.post('/local-models')
    async def switch(request: Request):
        if not authorized(request): return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        if lock.locked(): return JSONResponse({'error': 'Ya se está cambiando el modelo'}, status_code=409)
        async with lock:
            old = get_config()
            try:
                body = await request.json()
                key = body.get('key') if isinstance(body, dict) else None
                available = profiles()
                if not isinstance(key, str) or key not in available:
                    raise ValueError('Modelo desconocido')
                values = available[key]
                model = Path(values['RINTHEL_LLAMA_MODEL_PATH']).expanduser()
                if not model.is_file() or model.stat().st_size < int(values.get('RINTHEL_MODEL_MIN_BYTES', '4')):
                    raise ValueError('El modelo falta o está incompleto')
                with model.open('rb') as stream:
                    if stream.read(4) != b'GGUF':
                        raise ValueError('El archivo no es un modelo GGUF')
                new = with_overrides(old, values)
                new.validate()
                result = catalogue(available, new)
                provider_path = root / 'data/pithagoras/home/.pi/agent/models.json'
                provider_before = provider_path.read_bytes()
                register_models(root, available)
            except (ValueError, ConfigError, OSError, KeyError, TypeError) as exc:
                return JSONResponse({'error': str(exc)}, status_code=400)
            try:
                if old.llama != new.llama or old.moe != new.moe or not await managed.check_ready(old, LLAMA_SERVICE):
                    await managed.phase_kill(old, Report(), service=LLAMA_SERVICE)
                    await launch(new)
                # Persist only a model that has actually become ready.
                update_env_file(root / '.env', model_env_overrides(values))
                set_config(new)
                return {**result, 'busy': False}
            except Exception as exc:
                provider_path.write_bytes(provider_before)
                try:
                    await managed.phase_kill(new, Report(), service=LLAMA_SERVICE)
                    await launch(old)
                except Exception:
                    return JSONResponse({'error': f'{exc} No se pudo restaurar el modelo anterior.'}, status_code=500)
                return JSONResponse({'error': f'{exc} Se restauró el modelo anterior.'}, status_code=500)

    router.model_lock = lock
    return router
