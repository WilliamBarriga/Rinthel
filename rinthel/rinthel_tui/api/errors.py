"""Domain errors as HTTP answers: each area declares a table ``domain error
-> status and detail`` (``ERRORS`` next to its routes) and ``install_errors``
registers every table once, in ``create_app``. A route never catches a
domain error to translate it by hand."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class Reply:
    """What the daemon answers: ``{"detail": detail}`` with ``status``."""

    status: int
    detail: Any


# A fixed ``Reply``, or a function of the error when the detail carries it (``str(exc)``).
Answer = Reply | Callable[[Any], Reply]
ErrorTable = Mapping[type[Exception], Answer]


def coded(status: int, code: str) -> Callable[[Exception], Reply]:
    """``{"code", "message"}``: the code is what a client branches on, the
    message is the error's own text."""
    return lambda exc: Reply(status, {"code": code, "message": str(exc)})


def install_errors(app: FastAPI, *tables: ErrorTable) -> None:
    """Registers the areas' tables; the same class in two tables is a wiring error."""
    seen: dict[type[Exception], int] = {}
    for index, table in enumerate(tables):
        for error, answer in table.items():
            if error in seen:
                raise ValueError(f"{error.__name__} is in two error tables ({seen[error]} and {index})")
            seen[error] = index
            app.add_exception_handler(error, _handler(answer))


def _handler(answer: Answer):
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        reply = answer if isinstance(answer, Reply) else answer(exc)
        return JSONResponse({"detail": reply.detail}, status_code=reply.status)

    return handle
