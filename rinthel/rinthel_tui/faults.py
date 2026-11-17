"""La inyección de fallos de los dobles en memoria (ADR 0005), una sola para todos.

``fail_next(op, exc)`` hace que la próxima llamada a ``op`` levante ``exc`` antes de tocar nada; las siguientes andan.
``op`` es el nombre de un método público del doble (un puerto): uno que no existe es un ``ValueError``, así un typo no
pasa de largo. Se pueden encolar varios fallos de una misma ``op`` (``times=n`` encola ``n``).

Un doble hereda ``FailNext`` y ya está: cada método público que define arranca por revisar la cola. Si una ``op`` no
corresponde a un método (el fallo se dispara adentro de otro), el doble declara ``_OPS`` y llama ``self._enter(op)``
donde corresponde.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any


class FailureQueue:
    """Las fallas encoladas por operación y su validación. Un doble que cuenta cada llamada en un registro (los de
    lifecycle) hereda esto y llama ``_enter`` él mismo, en el punto donde quiere que falle; el resto hereda
    ``FailNext``."""

    _OPS: frozenset[str] | None = None

    def fail_next(self, op: str, exc: BaseException, *, times: int = 1) -> None:
        if op not in self._operations():
            raise ValueError(f"{type(self).__name__} has no operation {op!r}; one of {sorted(self._operations())}")
        self.__dict__.setdefault("_failures", {}).setdefault(op, []).extend([exc] * times)

    def fail_next_all(self, exc: BaseException, *, times: int = 1) -> None:
        """``times`` fallas de ``exc`` para cada operación: el doble entero «caído» (el equivalente de romper la
        infraestructura real en una suite de contrato)."""
        for op in sorted(self._operations()):
            self.fail_next(op, exc, times=times)

    def _operations(self) -> frozenset[str]:
        if self._OPS is not None:
            return self._OPS
        return frozenset(
            name
            for name in dir(type(self))
            if not name.startswith("_") and name not in ("fail_next", "fail_next_all") and callable(getattr(type(self), name))
        )

    def _enter(self, op: str) -> None:
        queued = self.__dict__.get("_failures", {}).get(op)
        if queued:
            raise queued.pop(0)


class FailNext(FailureQueue):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls._OPS is not None:
            return
        for name, member in list(cls.__dict__.items()):
            if name.startswith("_") or name in ("fail_next", "fail_next_all") or not inspect.isfunction(member):
                continue
            setattr(cls, name, _guarded(name, member))


def _guarded(op: str, method: Any) -> Any:
    if inspect.iscoroutinefunction(method):

        @functools.wraps(method)
        async def acall(self: FailNext, *args: Any, **kwargs: Any) -> Any:
            self._enter(op)
            return await method(self, *args, **kwargs)

        return acall

    @functools.wraps(method)
    def call(self: FailNext, *args: Any, **kwargs: Any) -> Any:
        self._enter(op)
        return method(self, *args, **kwargs)

    return call
