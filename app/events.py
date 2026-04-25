from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any


class EventBus:
    """Пер-сессионная шина событий для SSE.

    Использует asyncio.Queue, но публиковать можно и из других потоков
    через loop.call_soon_threadsafe.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._last: dict[str, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues[session_id].append(q)
        if session_id in self._last:
            q.put_nowait(self._last[session_id])
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        lst = self._queues.get(session_id, [])
        if q in lst:
            lst.remove(q)

    def publish(self, session_id: str, event: str, progress: float | None = None, **extra: Any) -> None:
        payload = {
            "event": event,
            "progress": progress,
            "ts": time.time(),
            **extra,
        }
        # Терминальные события — финал сессии. Не храним их вечно: после
        # них никто уже не подпишется на ретроспективное последнее событие.
        if event in ("done", "error"):
            self._last.pop(session_id, None)
            self._queues.pop(session_id, None)
        else:
            self._last[session_id] = payload
        subs = list(self._queues.get(session_id, []))
        if not subs:
            return
        if self._loop is None:
            for q in subs:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
            return
        self._loop.call_soon_threadsafe(_fanout, subs, payload)


def _fanout(subs: list[asyncio.Queue], payload: dict[str, Any]) -> None:
    for q in subs:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


bus = EventBus()
