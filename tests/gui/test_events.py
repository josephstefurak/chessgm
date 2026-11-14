"""The event stream: the generator on its own, then once through a real socket."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator

import httpx2 as httpx
import pytest
import uvicorn

from tests.gui.fakes import ScriptedEngine, make_session
from webgui.server.app import create_app
from webgui.server.events import KEEP_ALIVE, state_stream


def parse(event: str) -> dict[str, object]:
    assert event.startswith("event: state\ndata: ") and event.endswith("\n\n")
    data: dict[str, object] = json.loads(event.removeprefix("event: state\ndata: "))
    return data


def test_stream_sends_the_state_at_once_then_each_change_then_heartbeats() -> None:
    session, engine, _ = make_session()

    async def scenario() -> None:
        stream = state_stream(session, heartbeat=0.05)
        first = parse(await anext(stream))
        assert first["plies"] == []

        session.move(str(first["game_id"]), 0, "e2e4")
        second = parse(await asyncio.wait_for(anext(stream), timeout=1))
        plies = second["plies"]
        assert isinstance(plies, list) and len(plies) == 1

        # A change made on another thread (as the engine does) wakes the stream too.
        threading.Thread(target=lambda: engine.reply("e7e5")).start()
        third = parse(await asyncio.wait_for(anext(stream), timeout=1))
        plies = third["plies"]
        assert isinstance(plies, list) and len(plies) == 2

        assert await asyncio.wait_for(anext(stream), timeout=1) == KEEP_ALIVE
        await stream.aclose()

    asyncio.run(scenario())
    assert session._listeners == []  # closing the stream unsubscribed it


def test_a_late_subscriber_gets_only_the_current_state() -> None:
    session, engine, _ = make_session()
    start = session.snapshot()
    session.move(start.game_id, 0, "e2e4")
    engine.reply("e7e5")

    async def scenario() -> dict[str, object]:
        stream = state_stream(session, heartbeat=0.05)
        event = parse(await anext(stream))
        assert await asyncio.wait_for(anext(stream), timeout=1) == KEEP_ALIVE  # no backlog follows
        await stream.aclose()
        return event

    event = asyncio.run(scenario())
    plies = event["plies"]
    assert isinstance(plies, list) and len(plies) == 2


@pytest.fixture
def live_server() -> Iterator[str]:
    """The real application on a real socket, with the scripted engine."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(engine=ScriptedEngine(delay=0.01), port=port, think_seconds=0.1, static_dir=None)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive(), "server did not shut down with an event stream open"


def test_events_over_a_real_connection(live_server: str) -> None:
    def next_state(lines: Iterator[str]) -> dict[str, object]:
        for line in lines:
            if line.startswith("data: "):
                data: dict[str, object] = json.loads(line.removeprefix("data: "))
                return data
        raise AssertionError("stream ended")

    with (
        httpx.Client(base_url=live_server, timeout=5) as client,
        client.stream("GET", "/api/events") as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        lines = response.iter_lines()
        first = next_state(lines)
        assert first["plies"] == []

        body = {"game_id": first["game_id"], "ply": 0, "uci": "e2e4"}
        posted = httpx.post(f"{live_server}/api/move", json=body, headers={"origin": live_server})
        assert posted.status_code == 200

        # The scripted engine answers 1...g5; the stream must reach that state.
        deadline = time.monotonic() + 5
        while True:
            assert time.monotonic() < deadline
            plies = next_state(lines)["plies"]
            assert isinstance(plies, list)
            if len(plies) == 2:
                assert [ply["san"] for ply in plies] == ["e4", "g5"]
                break
