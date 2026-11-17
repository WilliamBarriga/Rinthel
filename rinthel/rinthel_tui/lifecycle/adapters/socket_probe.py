import asyncio
import socket
import urllib.error
import urllib.request


class SocketProbe:
    """``Probe`` con un ``connect`` TCP a localhost y un GET con urllib, cada
    uno en un hilo para no frenar el loop."""

    async def port_open(self, port: int) -> bool:
        def _check() -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("127.0.0.1", port)) == 0

        return await asyncio.to_thread(_check)

    async def http_ok(self, url: str, timeout: float = 2.0) -> bool:
        def _check() -> bool:
            try:
                with urllib.request.urlopen(url, timeout=timeout):
                    return True
            except urllib.error.HTTPError as exc:
                exc.close()
                return False
            except OSError:
                return False

        return await asyncio.to_thread(_check)
