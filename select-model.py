#!/usr/bin/env python3
"""Select a local model while Rinthel services and daemon are stopped."""
import os
import shutil
import socket
import sys
import time
from pathlib import Path

from rinthel_tui.config import default_config, with_overrides
from rinthel_tui.env_file import update_env_file
from rinthel_tui.local_models import load_profiles, model_env_overrides, register_models


def main() -> None:
    root = Path(__file__).resolve().parent
    profiles = load_profiles(root)
    argument = sys.argv[1] if len(sys.argv) > 1 else ''
    key = {'qwen': 'qwen3.6-35b-a3b', 'nemotron': 'nemotron-3-nano-30b-a3b'}.get(argument, argument)
    if key not in profiles:
        sys.exit('Uso: python3 select-model.py <clave del catálogo> (con Rinthel detenido)')
    cfg = default_config()
    ports = (int(os.environ.get('RINTHEL_DAEMON_PORT', '8765')),
             cfg.llama.port, cfg.pithagoras.port, cfg.understory.port)
    for port in ports:
        with socket.socket() as connection:
            connection.settimeout(0.5)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                sys.exit('Detén los servicios y el daemon antes de usar el selector offline')
    values = profiles[key]
    model = Path(values['RINTHEL_LLAMA_MODEL_PATH']).expanduser()
    if not model.is_file() or model.stat().st_size < int(values.get('RINTHEL_MODEL_MIN_BYTES', '4')):
        sys.exit('El modelo falta o está incompleto')
    with model.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            sys.exit('El archivo no es un modelo GGUF')
    with_overrides(cfg, values).validate()
    env = root / '.env'
    shutil.copy2(env, str(env) + '.backup-' + str(time.time_ns()))
    register_models(root, profiles)
    update_env_file(env, model_env_overrides(values))
    print('Modelo seleccionado:', key, '— inicia Rinthel y elige BOOT.')


if __name__ == '__main__':
    main()
