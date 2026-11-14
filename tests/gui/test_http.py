"""The HTTP layer: validation at the boundary, the local-only checks, response headers.

The last section enumerates every route the application exposes and fails until
each one is classified, so a new route cannot ship without its checks.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.gui.fakes import ManualEngine
from webgui.server.app import create_app
from webgui.server.security import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = {"origin": BASE}
INDEX_HTML = "<!doctype html><title>chessgm</title>"


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX_HTML)
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    return create_app(engine=ManualEngine(), port=PORT, think_seconds=2.0, static_dir=tmp_path)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=BASE) as test_client:
        yield test_client


def state(client: TestClient) -> dict[str, Any]:
    data: dict[str, Any] = client.get("/api/state").json()
    return data


def move_body(client: TestClient, uci: str = "e2e4") -> dict[str, Any]:
    current = state(client)
    return {"game_id": current["game_id"], "ply": len(current["plies"]), "uci": uci}


# --------------------------------------------------------------- happy paths


def test_state_is_the_full_snapshot(client: TestClient) -> None:
    response = client.get("/api/state")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "game_id", "version", "human", "status", "result", "turn", "start_fen", "plies", "legal",
        "actions", "time_control", "time_controls", "clock", "engine", "pgn",
    }  # fmt: skip
    assert body["human"] == "white" and body["status"] == "playing"


def test_a_move_returns_the_new_snapshot(client: TestClient) -> None:
    response = client.post("/api/move", json=move_body(client), headers=ORIGIN)
    assert response.status_code == 200
    body = response.json()
    assert [ply["san"] for ply in body["plies"]] == ["e4"]
    assert body["engine"]["state"] == "thinking"


def test_new_game_takeback_and_resign(client: TestClient, app: FastAPI) -> None:
    engine: ManualEngine = app.state.session._engine
    game = client.post("/api/game", json={"human": "white", "time_control": "5+3"}, headers=ORIGIN).json()
    assert game["time_control"] == "5+3" and game["clock"]["white_ms"] == 300_000

    client.post("/api/move", json=move_body(client), headers=ORIGIN)
    engine.reply("e7e5")
    back = client.post("/api/takeback", json={"game_id": game["game_id"], "ply": 2}, headers=ORIGIN)
    assert back.status_code == 200 and back.json()["plies"] == []

    over = client.post("/api/resign", json={"game_id": game["game_id"]}, headers=ORIGIN)
    assert over.status_code == 200
    assert over.json()["result"] == {"winner": "black", "reason": "resignation"}


def test_pgn_is_a_download(client: TestClient) -> None:
    client.post("/api/move", json=move_body(client), headers=ORIGIN)
    response = client.get("/api/pgn")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-chess-pgn")
    assert response.headers["content-disposition"] == 'attachment; filename="chessgm-game.pgn"'
    assert "1. e4 *" in response.text


def test_the_page_and_its_assets_are_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200 and page.text == INDEX_HTML
    assert page.headers["cache-control"] == "no-store"
    asset = client.get("/assets/app-abc123.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/assets/../index.html").status_code in (200, 404)  # never outside the build
    assert client.get("/assets/missing.js").status_code == 404


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"game_id": "0" * 16, "ply": 0},
        {"game_id": "0" * 16, "ply": 0, "uci": "e2e4", "extra": 1},
        {"game_id": "0" * 16, "ply": "0", "uci": "e2e4"},
        {"game_id": "0" * 16, "ply": -1, "uci": "e2e4"},
        {"game_id": "0" * 16, "ply": 0, "uci": "e2e9"},
        {"game_id": "0" * 16, "ply": 0, "uci": "0000"},
        {"game_id": "0" * 16, "ply": 0, "uci": "e2e4; rm -rf /"},
        {"game_id": "../../etc/passwd", "ply": 0, "uci": "e2e4"},
        {"game_id": 7, "ply": 0, "uci": "e2e4"},
        [],
        "e2e4",
    ],
)
def test_malformed_moves_are_refused_without_echoing_them(client: TestClient, body: object) -> None:
    response = client.post("/api/move", json=body, headers=ORIGIN)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert state(client)["plies"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"human": "green", "time_control": None},
        {"human": "white"},
        {"human": "white", "time_control": "5 + 3"},
        {"human": "white", "time_control": 5},
        {"human": "white", "time_control": None, "fen": "8/8/8/8/8/8/8/8 w - - 0 1"},
    ],
)
def test_malformed_new_game_requests_are_refused(client: TestClient, body: object) -> None:
    before = state(client)["game_id"]
    response = client.post("/api/game", json=body, headers=ORIGIN)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}
    assert state(client)["game_id"] == before


def test_broken_json_is_refused(client: TestClient) -> None:
    headers = {**ORIGIN, "content-type": "application/json"}
    response = client.post("/api/move", content=b"{not json", headers=headers)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}


def test_game_errors_carry_a_code_and_the_current_state(client: TestClient) -> None:
    illegal = client.post("/api/move", json=move_body(client, "e2e5"), headers=ORIGIN)
    assert illegal.status_code == 422
    assert illegal.json()["error"] == "illegal_move" and illegal.json()["state"]["plies"] == []

    stale = client.post("/api/move", json={**move_body(client), "ply": 4}, headers=ORIGIN)
    assert stale.status_code == 409 and stale.json()["error"] == "stale_position"

    unknown = client.post("/api/game", json={"human": "white", "time_control": "1+1"}, headers=ORIGIN)
    assert unknown.status_code == 422 and unknown.json()["error"] == "unknown_time_control"


# ------------------------------------------------------------ local-only gate


def test_a_post_without_this_servers_origin_is_refused(client: TestClient) -> None:
    body = move_body(client)
    for headers in (
        {},
        {"origin": "http://evil.example"},
        {"origin": "http://127.0.0.1:9999"},
        {"origin": "null"},
    ):
        response = client.post("/api/move", json=body, headers=headers)
        assert response.status_code == 403, headers
        assert response.json() == {"error": "forbidden_origin"}
    assert state(client)["plies"] == []


def test_localhost_is_accepted_as_well_as_the_loopback_address(app: FastAPI) -> None:
    with TestClient(app, base_url=f"http://localhost:{PORT}") as client:
        body = move_body(client)
        response = client.post("/api/move", json=body, headers={"origin": f"http://localhost:{PORT}"})
        assert response.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1:9999", "127.0.0.1", ""])
def test_any_other_host_header_is_refused(client: TestClient, host: str) -> None:
    for response in (
        client.get("/api/state", headers={"host": host}),
        client.get("/", headers={"host": host}),
        client.post("/api/move", json={}, headers={**ORIGIN, "host": host}),
    ):
        assert response.status_code == 403
        assert response.json() == {"error": "forbidden_host"}


def test_the_origin_is_checked_before_the_body_is_read(client: TestClient) -> None:
    response = client.post("/api/move", content=b"{not json", headers={"content-type": "application/json"})
    assert response.status_code == 403  # not 422: the body was never parsed


def test_posts_must_be_small_json(client: TestClient) -> None:
    body = move_body(client)
    form = client.post("/api/move", data={"uci": "e2e4"}, headers=ORIGIN)
    assert form.status_code == 415 and form.json() == {"error": "json_required"}

    padded = {**body, "uci": "e2e4" + " " * MAX_BODY_BYTES}
    large = client.post("/api/move", json=padded, headers=ORIGIN)
    assert large.status_code == 413 and large.json() == {"error": "body_too_large"}
    assert state(client)["plies"] == []


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS"])
def test_other_methods_do_not_exist(client: TestClient, method: str) -> None:
    response = client.request(method, "/api/move", headers=ORIGIN)
    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


def test_every_response_carries_the_security_headers(client: TestClient) -> None:
    responses = [
        client.get("/"),
        client.get("/api/state"),
        client.get("/assets/app-abc123.js"),
        client.get("/nope"),
        client.post("/api/move", json={}, headers=ORIGIN),
        client.post("/api/move", json={}),
        client.get("/api/state", headers={"host": "evil.example"}),
    ]
    for response in responses:
        headers = response.headers
        assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-origin" not in headers
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "unsafe" not in CONTENT_SECURITY_POLICY


def test_the_interactive_docs_are_off(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_too_many_event_streams_are_turned_away(app: FastAPI) -> None:
    from webgui.server.app import MAX_EVENT_STREAMS, _Counter

    counter = _Counter(MAX_EVENT_STREAMS)
    assert all(counter.take() for _ in range(MAX_EVENT_STREAMS))
    assert counter.take() is False
    counter.give_back()
    assert counter.take() is True


# ------------------------------------------------------- route classification

# Every route must appear here. "read" routes change nothing and answer GET only.
# "mutating" routes change the game and must sit behind the Origin check.
CLASSIFIED: dict[tuple[str, str], str] = {
    ("GET", "/"): "read",
    ("MOUNT", "/assets"): "read",
    ("GET", "/api/state"): "read",
    ("GET", "/api/events"): "read",
    ("GET", "/api/pgn"): "read",
    ("POST", "/api/game"): "mutating",
    ("POST", "/api/move"): "mutating",
    ("POST", "/api/takeback"): "mutating",
    ("POST", "/api/resign"): "mutating",
}


def routes_of(app: FastAPI) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            found.update((method, route.path) for method in route.methods or ())
        elif isinstance(route, Mount):
            found.add(("MOUNT", route.path))
        else:
            raise TypeError(f"unclassifiable route: {route!r}")
    return found


def test_every_route_is_classified(app: FastAPI) -> None:
    assert routes_of(app) == set(CLASSIFIED)


def test_read_routes_are_get_only_and_mutating_routes_are_gated(client: TestClient) -> None:
    for (method, path), kind in CLASSIFIED.items():
        if kind == "read":
            assert method in ("GET", "MOUNT"), path
        else:
            assert method == "POST", path
            assert client.post(path, json={}).status_code == 403, path  # no Origin
            assert client.post(path, json={}, headers={"origin": "http://evil.example"}).status_code == 403, (
                path
            )
