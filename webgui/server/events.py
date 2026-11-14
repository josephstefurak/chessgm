"""The live stream of game state sent to the browser (server-sent events).

Latest wins: a subscriber is only ever sent the current snapshot, never a backlog.
A reconnecting browser or a second tab therefore needs no replay logic, and a slow
reader cannot make the server queue anything up.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncGenerator, Callable

from webgui.server.session import GameSession

HEARTBEAT_SECONDS = 15.0  # a comment line this often keeps idle connections open
KEEP_ALIVE = ": keep-alive\n\n"


class StopSignal:
    """Set once, when the server begins to shut down. Every open stream then ends by
    itself. Without this the server waits on connections that never close, gives up,
    cancels them and logs each cancellation as an error. Safe to set from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._set = False
        self._listeners: list[Callable[[], None]] = []

    def is_set(self) -> bool:
        with self._lock:
            return self._set

    def set(self) -> None:
        with self._lock:
            self._set = True
            listeners = list(self._listeners)
        for listener in listeners:
            listener()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """`listener` is called when the signal is set. Returns the unsubscribe."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe


def format_event(data: str) -> str:
    return f"event: state\ndata: {data}\n\n"


async def state_stream(
    session: GameSession, heartbeat: float = HEARTBEAT_SECONDS, stop: StopSignal | None = None
) -> AsyncGenerator[str, None]:
    """Yields the current snapshot at once, then again after every change, and ends
    when `stop` is set."""
    stop = stop or StopSignal()
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()

    def on_change() -> None:  # called from engine, timer and request threads
        loop.call_soon_threadsafe(wake.set)

    unsubscribe = session.subscribe(on_change)
    unwatch = stop.subscribe(on_change)
    try:
        sent_version = -1
        while True:
            wake.clear()
            if stop.is_set():  # checked after the clear, so a stop is never slept through
                return
            snapshot = session.snapshot()
            if snapshot.version != sent_version:
                sent_version = snapshot.version
                yield format_event(snapshot.model_dump_json())
            try:
                await asyncio.wait_for(wake.wait(), timeout=heartbeat)
            except TimeoutError:
                yield KEEP_ALIVE
    finally:
        unwatch()
        unsubscribe()
