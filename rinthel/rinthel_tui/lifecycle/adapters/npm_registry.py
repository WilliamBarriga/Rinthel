import asyncio
import json
import urllib.error
import urllib.request

NPM_REGISTRY = "https://registry.npmjs.org"


class NpmRegistry:
    """``PackageRegistry`` sobre el registry de npm; ``registry`` es lo que
    varía (por defecto el público)."""

    def __init__(self, *, registry: str = NPM_REGISTRY) -> None:
        self._registry = registry

    async def latest(self, package: str, timeout: float = 5.0) -> str | None:
        def _fetch() -> str | None:
            try:
                with urllib.request.urlopen(f"{self._registry}/{package}/latest", timeout=timeout) as resp:
                    return json.load(resp)["version"]
            except urllib.error.HTTPError as exc:
                exc.close()
                return None
            except (OSError, ValueError, KeyError):
                return None

        return await asyncio.to_thread(_fetch)
