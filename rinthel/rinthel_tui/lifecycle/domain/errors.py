"""Los errores del dominio de lifecycle: los puertos no dejan pasar la
excepción del motor (OSError), cada seam habla con la suya."""


class SpawnFailed(Exception):
    """El proceso no pudo arrancar (el binario no existe, no es ejecutable)."""


class DataDirError(Exception):
    """No se pudo crear un directorio de datos (sin permisos, el padre es un archivo)."""


class PhaseError(Exception):
    """Fallo esperado de una fase (equivalente al `exit 1` de bash)."""
