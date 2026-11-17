"""``tail(path)``: lo propio del adapter ``FileLog`` contra un archivo real en
``tmp_path`` — backlog, append, truncado, rotación por inode, archivo que
aparece después de conectar y archivo que desaparece."""

import asyncio
import dataclasses

import pytest

from rinthel_tui.clock import ManualClock
from rinthel_tui.monitoring.adapters.log_file import FileLog, tail

POLL = 0.01


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


async def lines(source, n: int) -> list[str]:
    return [await asyncio.wait_for(anext(source), timeout=1) for _ in range(n)]


async def polls(clock: ManualClock, n: int) -> None:
    """Deja que el ``tail`` mire el archivo ``n`` veces más: espera sus
    ``sleep`` del reloj, no tiempo."""
    target = len(clock.sleeps) + n
    while len(clock.sleeps) < target:
        await asyncio.sleep(0)


def append(path, text: str) -> None:
    with path.open("a") as f:
        f.write(text)


async def test_sends_the_backlog_then_appended_lines(clock, tmp_path):
    log = tmp_path / "llama.log"
    log.write_text("uno\ndos\ntres\n")
    source = tail(log, backlog=2, poll=POLL, clock=clock)

    assert await lines(source, 2) == ["dos", "tres"]
    append(log, "cuatro\n")
    assert await lines(source, 1) == ["cuatro"]


async def test_missing_file_sends_one_waiting_line_then_tails_once_it_appears(clock, tmp_path):
    log = tmp_path / "llama.log"
    source = tail(log, poll=POLL, clock=clock)

    assert await lines(source, 1) == [f"[daemon] esperando {log}"]
    pending = asyncio.ensure_future(anext(source))
    await polls(clock, 5)
    assert not pending.done()  # una sola línea de espera, no una por tick

    log.write_text("arrancó\n")
    assert await asyncio.wait_for(pending, timeout=1) == "arrancó"


async def test_truncated_file_is_read_again_from_the_start(clock, tmp_path):
    log = tmp_path / "llama.log"
    log.write_text("una línea bastante larga de antes\n")
    source = tail(log, backlog=0, poll=POLL, clock=clock)
    first = asyncio.ensure_future(anext(source))
    await polls(clock, 3)

    log.write_text("corta\n")
    assert await asyncio.wait_for(first, timeout=1) == "corta"


async def test_rotated_file_is_followed_by_inode_even_if_it_is_already_larger(clock, tmp_path):
    log = tmp_path / "llama.log"
    log.write_text("vieja\n")
    source = tail(log, backlog=0, poll=POLL, clock=clock)
    first = asyncio.ensure_future(anext(source))
    await polls(clock, 3)

    log.rename(tmp_path / "llama.log.1")
    log.write_text("nueva línea uno\nnueva línea dos\n")
    assert await asyncio.wait_for(first, timeout=1) == "nueva línea uno"
    assert await lines(source, 1) == ["nueva línea dos"]


async def test_a_line_written_in_pieces_arrives_whole(clock, tmp_path):
    log = tmp_path / "llama.log"
    log.write_text("")
    source = tail(log, backlog=0, poll=POLL, clock=clock)
    first = asyncio.ensure_future(anext(source))

    with log.open("ab") as f:
        f.write(b"slot 0: tama" + "ñ".encode()[:1])
        f.flush()
        await polls(clock, 3)
        f.write("ñ".encode()[1:] + b"o 512\n")

    assert await asyncio.wait_for(first, timeout=1) == "slot 0: tamaño 512"


async def test_a_file_that_disappears_goes_back_to_waiting_without_resending_the_backlog(clock, tmp_path):
    log = tmp_path / "llama.log"
    log.write_text("vieja\n")
    source = tail(log, backlog=1, poll=POLL, clock=clock)
    assert await lines(source, 1) == ["vieja"]
    pending = asyncio.ensure_future(anext(source))
    await polls(clock, 3)

    log.unlink()
    assert await asyncio.wait_for(pending, timeout=1) == f"[daemon] esperando {log}"
    log.write_text("nueva\n")
    assert await lines(source, 1) == ["nueva"]


async def test_each_follow_reads_the_log_path_of_the_current_cfg(cfg, clock, tmp_path):
    """Un cambio de ``llama.log`` por ``POST /config`` se aplica al
    reconectar: cada ``follow`` (una por conexión) lee el ``cfg`` vivo."""
    old, new = tmp_path / "vieja.log", tmp_path / "nueva.log"
    old.write_text("de la vieja\n")
    new.write_text("de la nueva\n")
    current = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, log=old))
    log = FileLog(lambda: current, poll=POLL, clock=clock)

    assert await lines(log.follow(), 1) == ["de la vieja"]
    current = dataclasses.replace(cfg, llama=dataclasses.replace(cfg.llama, log=new))
    assert await lines(log.follow(), 1) == ["de la nueva"]
