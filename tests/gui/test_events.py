"""The event stream: the generator on its own, then once through a real socket."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx2 as httpx
import pytest
import uvicorn

from tests.gui.fakes import ScriptedEngine, make_session
from webgui.server.app import create_app
from webgui.server.events import KEEP_ALIVE, StopSignal, state_stream
from webgui.server.runner import LocalServer

GRACE_SECONDS = 5  # long on purpose: a shutdown that has to wait this out fails the tests


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


def test_stream_ends_when_the_server_is_stopping() -> None:
    session, _, _ = make_session()
    stop = StopSignal()

    async def scenario() -> None:
        stream = state_stream(session, heartbeat=30, stop=stop)
        await anext(stream)
        threading.Timer(0.05, stop.set).start()  # from another thread, mid-wait
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), timeout=1)

    asyncio.run(scenario())
    assert session._listeners == [] and stop._listeners == []


def test_a_stream_opened_after_the_stop_ends_at_once() -> None:
    session, _, _ = make_session()
    stop = StopSignal()
    stop.set()

    async def scenario() -> list[str]:
        return [chunk async for chunk in state_stream(session, heartbeat=30, stop=stop)]

    assert asyncio.run(scenario()) == []


@dataclass
class Live:
    url: str
    server: LocalServer
    thread: threading.Thread


@pytest.fixture
def live_server() -> Iterator[Live]:
    """The real application on a real socket, with the scripted engine."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(engine=ScriptedEngine(delay=0.01), port=port, think_seconds=0.1, static_dir=None)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        log_config=None,  # leave logging alone so the tests can read what uvicorn reports
        timeout_graceful_shutdown=GRACE_SECONDS,
    )
    server = LocalServer(config, end_streams=app.state.end_streams)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.01)
    yield Live(f"http://127.0.0.1:{port}", server, thread)
    server.should_exit = True
    thread.join(timeout=GRACE_SECONDS + 5)
    assert not thread.is_alive(), "server did not shut down"


def test_events_over_a_real_connection(live_server: Live) -> None:
    url = live_server.url

    def next_state(lines: Iterator[str]) -> dict[str, object]:
        for line in lines:
            if line.startswith("data: "):
                data: dict[str, object] = json.loads(line.removeprefix("data: "))
                return data
        raise AssertionError("stream ended")

    with (
        httpx.Client(base_url=url, timeout=5) as client,
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
        posted = httpx.post(f"{url}/api/move", json=body, headers={"origin": url})
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


def test_shutdown_ends_open_streams_without_waiting_or_logging_errors(
    live_server: Live, caplog: pytest.LogCaptureFixture
) -> None:
    """What Ctrl-C does with the page still open. It used to wait out the grace
    period, cancel the stream and log a traceback."""
    with (
        caplog.at_level("ERROR"),
        httpx.Client(base_url=live_server.url, timeout=GRACE_SECONDS + 5) as client,
        client.stream("GET", "/api/events") as response,
    ):
        lines = response.iter_lines()
        assert next(lines) == "event: state"

        began = time.monotonic()
        live_server.server.should_exit = True
        for _ in lines:  # the server ends the stream; nothing here closes it
            pass
        live_server.thread.join(timeout=GRACE_SECONDS + 5)
        took = time.monotonic() - began

    assert not live_server.thread.is_alive()
    assert took < GRACE_SECONDS / 2, f"shutdown waited {took:.1f}s on an open stream"
    assert [record.getMessage() for record in caplog.records] == []
