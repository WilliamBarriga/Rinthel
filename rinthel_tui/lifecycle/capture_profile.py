"""Genera el perfil de ruteo de expertos que ``GGML_MOE_CACHE_PROFILE``
(rinthel_tui/config.py) apunta como cache para llama-server.

Reemplaza ``nightcity/tools/rinthel-capture-profile.sh``. Corre en
foreground: son 2 tareas sintéticas cortas contra el build EXPERIMENTAL
(llama-moe-trace), no el llama-server normal — no es parte del ciclo
BOOT/DOWN/RELOAD, por eso vive aparte de lifecycle/{phases,specs,runner}.py.
"""

import asyncio
import os
import tempfile
from pathlib import Path

from rinthel_tui.config import RinthelConfig
from rinthel_tui.lifecycle.phases import PhaseError, PhaseReport, _run

# Mismo contexto que carga `pi` de verdad (AGENTS.md ancestro + raíz del
# workspace) + ChatML, no texto suelto — distribución de expertos más
# real que un prompt genérico.
_ANCESTOR_AGENTS = Path("~/AGENTS.md").expanduser()
_ROOT_AGENTS = Path("~/CodeBase/AGENTS.md").expanduser()

CODE_TASK = (
    "Encontre un bug puntual: en un script de PowerShell de este workspace, "
    "una variable de entorno se define con $env: pero nunca se limpia con "
    "Remove-Item al final, asi que queda pisando la siguiente corrida. "
    "Mostrame como quedaria el fix minimo, sin tocar nada mas del script."
)
CHAT_TASK = (
    "Tengo un archivo manifest.md en knowledge/snippets/ que no sigue el "
    "manifest_template.md. Explicame en dos o tres oraciones que campos le "
    "faltarian tipicamente y por que importan para el paso de indexado, sin "
    "leer el repo entero."
)


def _chatml_prompt(system_text: str, user_text: str) -> str:
    return (
        f"<|im_start|>system\n{system_text}<|im_end|>\n"
        f"<|im_start|>user\n{user_text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


async def _run_trace(cfg: RinthelConfig, prompt: str, out_file: Path, report: PhaseReport) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_path = Path(f.name)
    try:
        env = os.environ.copy()
        env["MOE_TRACE_OUT"] = str(out_file)
        rc = await _run(
            [
                str(cfg.moe_trace_build), "-m", str(cfg.model),
                "-ngl", "99", "-ncmoe", "99", "-fa", "1", "-c", "40096", "-n", "512",
                "-f", str(prompt_path),
            ],
            report,
            env=env,
        )
        if rc != 0:
            raise PhaseError(f"llama-moe-trace salió con código {rc} generando {out_file.name}")
    finally:
        prompt_path.unlink(missing_ok=True)


async def capture_profile(cfg: RinthelConfig, report: PhaseReport) -> None:
    system_text = f"{_ANCESTOR_AGENTS.read_text()}\n\n{_ROOT_AGENTS.read_text()}"

    cfg.moe_trace_out_dir.mkdir(parents=True, exist_ok=True)
    code_csv = cfg.moe_trace_out_dir / "qwen3.6-code.csv"
    chat_csv = cfg.moe_trace_out_dir / "qwen3.6-chat.csv"

    report.info("Capturando perfil 'código'...")
    await _run_trace(cfg, _chatml_prompt(system_text, CODE_TASK), code_csv, report)

    report.info("Capturando perfil 'chat'...")
    await _run_trace(cfg, _chatml_prompt(system_text, CHAT_TASK), chat_csv, report)

    cfg.moe_cache_profile.write_text(code_csv.read_text() + chat_csv.read_text())
    report.success(f"Listo: {cfg.moe_cache_profile}")
