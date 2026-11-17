"""Un recurso que cuenta cuántas veces lo cerraron, para los tests de
``Resources``."""


class CountingResource:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1
