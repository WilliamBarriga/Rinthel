"""INSTALL from the shell: ``python -m rinthel_tui.install [--voice]``.

Asks the running daemon (``POST /install``) with the Instance's service
secret, so INSTALL runs under the global lifecycle lock and the daemon's live
config follows it. ``--voice`` (opt-in, Linux only) adds whisper.cpp and
audio.cpp at their pins, their default models and both entries active, and
starts ``stt``/``tts``; it is repeatable on an existing Instance. Progress is
in the TUI's log; here, one line per unit when it ends."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from rinthel_tui.instance import Instance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rinthel_tui.install")
    parser.add_argument("--root", type=Path, help="raíz explícita (default: Instance.discover())")
    parser.add_argument("--voice", action="store_true", help="también la voz local (stt/tts), solo Linux")
    args = parser.parse_args(argv)

    instance = Instance(args.root) if args.root else Instance.discover()
    port = instance.variable("RINTHEL_DAEMON_PORT") or "8765"
    secret = instance.variable("RINTHEL_SERVICE_SECRET") or ""
    print("INSTALL en curso — puede tardar mucho; el progreso está en la TUI", file=sys.stderr)
    try:
        response = httpx.post(
            f"http://127.0.0.1:{port}/install",
            json={"voice": args.voice},
            headers={"X-Rinthel-Service-Secret": secret},
            # Builds and downloads take as long as they take.
            timeout=httpx.Timeout(None, connect=5.0),
        )
    except httpx.HTTPError as exc:
        print(f"error: no hay daemon en :{port} ({exc}) — arrancalo con rinthel-boot.sh", file=sys.stderr)
        return 2
    if response.status_code != 200:
        print(f"error: el daemon respondió {response.status_code}: {response.text}", file=sys.stderr)
        return 2
    results = response.json()["results"]
    for result in results:
        print(f"{'ok ' if result['ok'] else 'ERR'} {result['service']}: {result['message']}")
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
