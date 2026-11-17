"""Chequeo de token compartido para hostexecd — mismo criterio que
UNDERSTORY_TOKEN: un secreto en un header de cada request, generado por
INSTALL o el boot en el ``.env`` raíz y comparado en tiempo constante."""

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
    equivocada no debe quedar abierto por accidente: los contenedores de la
    Instance llegan al host, así que sin token este daemon sería alcanzable
    desde cualquiera de ellos, no solo desde la sesión de Rinthel)."""
    expected = expected_token()
    if expected is None or not received:
        return False
    return hmac.compare_digest(received, expected)
