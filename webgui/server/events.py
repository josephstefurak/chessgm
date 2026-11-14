"""The live stream of game state sent to the browser (server-sent events).

Latest wins: a subscriber is only ever sent the current snapshot, never a backlog.
A reconnecting browser or a second tab therefore needs no replay logic, and a slow
reader cannot make the server queue anything up.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from webgui.server.session import GameSession

HEARTBEAT_SECONDS = 15.0  # a comment line this often keeps idle connections open
KEEP_ALIVE = ": keep-alive\n\n"


def format_event(data: str) -> str:
    return f"event: state\ndata: {data}\n\n"


async def state_stream(
    session: GameSession, heartbeat: float = HEARTBEAT_SECONDS
) -> AsyncGenerator[str, None]:
    """Yields the current snapshot at once, then again after every change."""
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()

    def on_change() -> None:  # called from engine, timer and request threads
        loop.call_soon_threadsafe(wake.set)

    unsubscribe = session.subscribe(on_change)
    try:
        sent_version = -1
        while True:
            wake.clear()
            snapshot = session.snapshot()
            if snapshot.version != sent_version:
                sent_version = snapshot.version
                yield format_event(snapshot.model_dump_json())
            try:
                await asyncio.wait_for(wake.wait(), timeout=heartbeat)
            except TimeoutError:
                yield KEEP_ALIVE
    finally:
        unsubscribe()
