"""Chequeo de token compartido para hostexecd — mismo criterio que
UNDERSTORY_TOKEN/PORTAL_SECRET: un secreto en un header de cada request,
generado por fuera (openssl rand -hex 32, ver .env.example) y comparado en
tiempo constante."""

from __future__ import annotations

import hmac
import os

TOKEN_HEADER = "X-Rinthel-Token"


def expected_token() -> str | None:
    """El token configurado, o None si no hay ninguno seteado."""
    token = os.getenv("RINTHEL_HOSTEXECD_TOKEN", "").strip()
    return token or None


def check_token(received: str | None) -> bool:
    """True solo si ``received`` matchea el token esperado. Comparación en
    tiempo constante (``hmac.compare_digest``) para no filtrar el valor
    correcto por timing.

    Sin ``RINTHEL_HOSTEXECD_TOKEN`` seteado, falla cerrado: nunca autentica,
    ni con header vacío — un daemon sin secreto propio en la máquina
    equivocada no debe quedar abierto por accidente (ver plan, decisión 5:
    Pithagoras y Understory comparten `network_mode: host`, así que sin
    token este daemon sería alcanzable desde cualquiera de los dos
    contenedores, no solo desde la sesión de Rinthel)."""
    expected = expected_token()
    if expected is None or not received:
        return False
    return hmac.compare_digest(received, expected)
