"""The HTTP face of the GUI: routes in, snapshots out.

No chess here. Each route validates its input (see `schemas.py`), hands the intent
to the `GameSession`, and returns the snapshot it gets back. Everything the
application depends on is passed to `create_app`, which is how the tests swap in
a scripted engine without the shipped code having any test switches.
"""

from __future__ import annotations

import threading
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from webgui.server import schemas as wire
from webgui.server.clock import PRESETS, TimeControl
from webgui.server.engine_port import EnginePort
from webgui.server.events import HEARTBEAT_SECONDS, StopSignal, state_stream
from webgui.server.security import LocalOnlyMiddleware
from webgui.server.session import GameSession, SessionError

MAX_EVENT_STREAMS = 8  # open tabs; more than this is not a person playing chess
PGN_FILENAME = "chessgm-game.pgn"


def create_app(
    *,
    engine: EnginePort,
    port: int,
    think_seconds: float,
    static_dir: Path | None,
    time_controls: Sequence[TimeControl] = PRESETS,
    now: Callable[[], float] = time.monotonic,
    heartbeat: float = HEARTBEAT_SECONDS,
) -> FastAPI:
    """`port` is the port the server will listen on; requests naming any other
    host or origin are refused. `static_dir` is the built UI (None serves the API only)."""
    session = GameSession(engine, think_seconds=think_seconds, time_controls=time_controls, now=now)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        session.close()

    # The interactive docs are off: they load scripts from a CDN and add routes nobody reviewed.
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.session = session
    stop_streams = StopSignal()
    app.state.end_streams = stop_streams.set  # called by the runner as shutdown begins
    streams = _Counter(MAX_EVENT_STREAMS)

    @app.exception_handler(SessionError)
    def session_error(_: Request, error: SessionError) -> JSONResponse:
        body = {"error": error.code, "state": session.snapshot().model_dump()}
        return JSONResponse(body, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # Deliberately says nothing about the input: it is not echoed back.
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    @app.get("/api/state")
    def get_state() -> wire.Snapshot:
        return session.snapshot()

    @app.get("/api/events")
    async def get_events() -> StreamingResponse:
        if not streams.take():
            return StreamingResponse(iter(()), status_code=503)

        async def stream() -> AsyncIterator[str]:
            try:
                async for chunk in state_stream(session, heartbeat, stop_streams):
                    yield chunk
            finally:
                streams.give_back()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/pgn")
    def get_pgn() -> PlainTextResponse:
        headers = {"content-disposition": f'attachment; filename="{PGN_FILENAME}"'}
        return PlainTextResponse(session.pgn(), media_type="application/x-chess-pgn", headers=headers)

    @app.post("/api/game")
    def post_game(body: wire.NewGameRequest) -> wire.Snapshot:
        return session.new_game(body.human, body.time_control)

    @app.post("/api/move")
    def post_move(body: wire.MoveRequest) -> wire.Snapshot:
        return session.move(body.game_id, body.ply, body.uci)

    @app.post("/api/takeback")
    def post_takeback(body: wire.TakebackRequest) -> wire.Snapshot:
        return session.takeback(body.game_id, body.ply)

    @app.post("/api/resign")
    def post_resign(body: wire.ResignRequest) -> wire.Snapshot:
        return session.resign(body.game_id)

    if static_dir is not None:
        index = static_dir / "index.html"

        @app.get("/")
        def get_index() -> FileResponse:
            return FileResponse(index, media_type="text/html")

        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    app.add_middleware(LocalOnlyMiddleware, port=port)
    return app


class _Counter:
    """A limit on how many of something are in use at once."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._in_use = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self._in_use >= self._limit:
                return False
            self._in_use += 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self._in_use -= 1
