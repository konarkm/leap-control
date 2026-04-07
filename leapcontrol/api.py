from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import websockets
from websockets.server import WebSocketServerProtocol


class LocalApiServer:
    def __init__(
        self,
        host: str,
        port: int,
        message_handler: Callable[[dict], Awaitable[None]],
        snapshot_provider: Callable[[], list[dict]] | None = None,
    ):
        self.host = host
        self.port = port
        self.message_handler = message_handler
        self.snapshot_provider = snapshot_provider
        self._server = None
        self._clients: set[WebSocketServerProtocol] = set()

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        await asyncio.gather(
            *(client.close() for client in list(self._clients)),
            return_exceptions=True,
        )

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        message = json.dumps(payload)
        stale = []
        for client in list(self._clients):
            try:
                await client.send(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        self._clients.add(websocket)
        try:
            await websocket.send(json.dumps({"type": "hello", "service": "leapcontrol"}))
            if self.snapshot_provider is not None:
                for payload in self.snapshot_provider():
                    await websocket.send(json.dumps(payload))
            async for raw in websocket:
                payload = json.loads(raw)
                await self.message_handler(payload)
        finally:
            self._clients.discard(websocket)
