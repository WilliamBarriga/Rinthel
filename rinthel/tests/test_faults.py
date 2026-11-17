"""La inyección de fallos compartida por todos los dobles en memoria (ADR 0005): ``fail_next(op, exc)`` hace que la
próxima llamada a ``op`` levante antes de tocar nada y que las siguientes anden. Cada doble prueba solo qué
operación rompe en su suite; la mecánica se prueba aquí, una vez."""

import pytest

from rinthel_tui.faults import FailNext, FailureQueue


class Down(Exception):
    pass


class Store(FailNext):
    def __init__(self) -> None:
        self.rows: list[str] = []

    def add(self, row: str) -> None:
        self.rows.append(row)

    def count(self) -> int:
        return len(self.rows)

    async def fetch(self) -> list[str]:
        return list(self.rows)


class Explicit(FailNext):
    _OPS = frozenset({"inside"})

    def outer(self) -> None:
        self._enter("inside")


class Logged(FailureQueue):
    _OPS = frozenset({"run"})

    def run(self) -> None:
        self._enter("run")


def test_the_next_call_fails_before_touching_anything_and_the_ones_after_it_work():
    store = Store()
    store.fail_next("add", Down("roto"))

    with pytest.raises(Down):
        store.add("a")
    assert store.rows == []

    store.add("a")
    assert store.rows == ["a"]


def test_failures_of_one_operation_do_not_touch_the_others():
    store = Store()
    store.fail_next("add", Down("roto"))

    assert store.count() == 0
    with pytest.raises(Down):
        store.add("a")


def test_queued_failures_come_out_in_order():
    store = Store()
    store.fail_next("add", Down("primero"))
    store.fail_next("add", Down("segundo"))

    with pytest.raises(Down, match="primero"):
        store.add("a")
    with pytest.raises(Down, match="segundo"):
        store.add("a")
    store.add("a")


def test_times_queues_that_many_failures():
    store = Store()
    store.fail_next("add", Down("roto"), times=2)

    for _ in range(2):
        with pytest.raises(Down):
            store.add("a")
    store.add("a")


def test_an_operation_the_double_does_not_have_is_a_typo():
    with pytest.raises(ValueError, match="ad"):
        Store().fail_next("ad", Down("roto"))


def test_a_private_method_is_not_an_operation():
    with pytest.raises(ValueError, match="_enter"):
        Store().fail_next("_enter", Down("roto"))


def test_fail_next_all_breaks_every_operation_once():
    store = Store()
    store.fail_next_all(Down("caído"))

    with pytest.raises(Down):
        store.add("a")
    with pytest.raises(Down):
        store.count()
    store.add("a")
    assert store.count() == 1


async def test_an_async_operation_fails_too():
    store = Store()
    store.fail_next("fetch", Down("roto"))

    with pytest.raises(Down):
        await store.fetch()
    assert await store.fetch() == []


def test_a_double_that_declares_its_operations_fires_where_it_says():
    double = Explicit()
    double.fail_next("inside", Down("roto"))

    with pytest.raises(Down):
        double.outer()
    with pytest.raises(ValueError, match="outer"):
        double.fail_next("outer", Down("roto"))


def test_a_failure_queue_alone_fires_only_where_the_double_enters():
    logged = Logged()
    logged.fail_next("run", Down("roto"))

    with pytest.raises(Down):
        logged.run()
    logged.run()
