"""Request checks and response headers for the local server.

A server on 127.0.0.1 can still be reached by any web page open in the browser,
so every request is checked before it reaches a route:

* Host must be this server's own address. This blocks DNS rebinding, where a
  hostile site points its own name at 127.0.0.1.
* Only GET, HEAD and POST exist. Every POST must carry this server's exact Origin
  (a missing Origin is refused), must be JSON, and must declare a small body.
  That is the CSRF check: another site cannot make the browser move pieces.
* No CORS headers are ever sent, so another origin cannot read a response either.

Written as plain ASGI middleware because the event stream is long-lived.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MAX_BODY_BYTES = 1024  # the largest real request is about 70 bytes
ASSET_PREFIX = "/assets/"

CSP_DIRECTIVES = (
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",  # chessground ships its piece set as data: images
    "font-src 'self'",
    "connect-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
)
CONTENT_SECURITY_POLICY = "; ".join(CSP_DIRECTIVES)

SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)

# Built assets have a content hash in their name, so they can be cached for good.
# Everything else (the page itself, game state) must always be fetched fresh.
CACHE_ASSET = b"public, max-age=31536000, immutable"
CACHE_NEVER = b"no-store"


def local_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def local_origins(port: int) -> frozenset[str]:
    return frozenset(f"http://{host}" for host in local_hosts(port))


class LocalOnlyMiddleware:
    def __init__(self, app: AsgiApp, *, port: int) -> None:
        self._app = app
        self._hosts = local_hosts(port)
        self._origins = local_origins(port)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._app(scope, receive, send)
            return
        if scope["type"] != "http":
            return  # no websockets here: refusing to answer closes the connection

        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        refusal = self._refusal(scope["method"], headers)
        if refusal is not None:
            await _refuse(send, *refusal)
            return

        cache = CACHE_ASSET if scope["path"].startswith(ASSET_PREFIX) else CACHE_NEVER

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"cache-control"
                ]
                message["headers"] = [*kept, *SECURITY_HEADERS, (b"cache-control", cache)]
            await send(message)

        await self._app(scope, receive, send_with_headers)

    def _refusal(self, method: str, headers: dict[bytes, bytes]) -> tuple[int, str] | None:
        if headers.get(b"host", b"").decode("latin-1") not in self._hosts:
            return 403, "forbidden_host"
        if method in ("GET", "HEAD"):
            return None
        if method != "POST":
            return 405, "method_not_allowed"
        if headers.get(b"origin", b"").decode("latin-1") not in self._origins:
            return 403, "forbidden_origin"
        media_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
        if media_type != b"application/json":
            return 415, "json_required"
        try:
            length = int(headers.get(b"content-length", b""))
        except ValueError:
            return 411, "length_required"
        if not 0 <= length <= MAX_BODY_BYTES:
            return 413, "body_too_large"
        return None


async def _refuse(send: Send, status: int, code: str) -> None:
    body = json.dumps({"error": code}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *SECURITY_HEADERS,
                (b"cache-control", CACHE_NEVER),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
