from __future__ import annotations

from typing import Any, Callable, Dict


class AsyncServer:
    """
    Placeholder for issue #5.

    Planned responsibilities:
    - asyncio stream server
    - per-connection multiplexed request handling
    - unified response envelope
    - graceful shutdown of in-flight tasks
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self._host = host
        self._port = port
        self._methods: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._methods[name] = func

    async def serve_forever(self) -> None:
        raise NotImplementedError("AsyncServer is reserved for issue #5")

    async def stop(self) -> None:
        raise NotImplementedError("AsyncServer is reserved for issue #5")
