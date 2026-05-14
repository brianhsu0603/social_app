"""Per-pod registry of active WebSocket connections, indexed by room_id.

This is intentionally local to one process. Cross-pod fan-out happens through
Kafka: each backend replica runs a consumer that pushes incoming messages to
whatever sockets it owns. See `app/workers/chat_consumer.py`.
"""

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._rooms[room_id].add(ws)

    async def disconnect(self, room_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms[room_id].discard(ws)
            if not self._rooms[room_id]:
                self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: int, payload: dict[str, Any]) -> None:
        targets = list(self._rooms.get(room_id, ()))
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                # Drop dead sockets quietly; the disconnect path will clean up.
                await self.disconnect(room_id, ws)


manager = WebSocketManager()
