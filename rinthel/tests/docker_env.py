"""Lo que necesitan las pruebas que corren contra un ``docker`` real (la pata
real de la suite de contrato de ``Compose``): saber si está, con la imagen
ya bajada, y saltear si no. Nunca bajan imágenes ni tocan los proyectos
compose de la Instance: cada prueba arma el suyo, con nombre propio."""

import os
import subprocess

import pytest

# Chica y de uso común; si no está bajada, la pata real se saltea.
IMAGE = "alpine:3"


def skip_or_fail(reason: str) -> None:
    """Lo que falta para correr (docker, la imagen): se saltea el test, salvo
    con ``RINTHEL_REQUIRE_DOCKER_TESTS=1``, donde falla."""
    if os.environ.get("RINTHEL_REQUIRE_DOCKER_TESTS"):
        pytest.fail(reason)
    pytest.skip(reason)


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False)


def docker_available(image: str = IMAGE) -> bool:
    try:
        return docker("info").returncode == 0 and docker("image", "inspect", image).returncode == 0
    except FileNotFoundError:
        return False
