"""Runs the application on a local socket until it is told to stop.

uvicorn waits for open connections before it shuts down. The page keeps an event
stream open for as long as it is on screen, so that wait always ran out; uvicorn
then cancelled the stream and logged the cancellation as an error, traceback and
all, on every Ctrl-C. `LocalServer` ends the streams first, so the connections
close by themselves and shutdown is quiet.
"""

from __future__ import annotations

import socket
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI


class LocalServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, *, end_streams: Callable[[], None]) -> None:
        super().__init__(config)
        self._end_streams = end_streams

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._end_streams()
        await super().shutdown(sockets)


def serve(app: FastAPI, *, host: str, port: int, grace_seconds: int) -> bool:
    """Blocks until interrupted. Returns False if the server never started.

    `grace_seconds` is how long shutdown waits for a request still in flight; it is
    a backstop only, since the event streams no longer hold it up."""
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=grace_seconds
    )
    server = LocalServer(config, end_streams=app.state.end_streams)
    try:
        server.run()
    except KeyboardInterrupt:
        pass  # uvicorn raises Ctrl-C again once it has finished shutting down
    return server.started
