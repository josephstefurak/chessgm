#!/usr/bin/env python3
"""Play against the engine in the browser.

    python gui.py                  # opens http://127.0.0.1:8765
    python gui.py --port 9000 --no-browser

The page is served from this machine only. Build the UI once before the first
run (see README.md, "Play in the browser").

This file is only the launcher: it checks its arguments, starts the local server
in `webgui/server`, and opens the browser.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from main import DEFAULT_THINK_SECONDS
from webgui.server.app import create_app
from webgui.server.engine_port import SearchEngine

HOST = "127.0.0.1"  # never anything else: this server is for this machine only
DEFAULT_PORT = 8765
UI_DIR = Path(__file__).resolve().parent / "webgui" / "web"
BUILD_DIR = UI_DIR / "dist"
BUILD_HELP = f"""The browser UI has not been built yet. Build it once with:

    cd {UI_DIR}
    npm install
    npm run build

then run this command again."""
SHUTDOWN_GRACE_SECONDS = 1  # open event streams would otherwise hold Ctrl-C up
BROWSER_WAIT_SECONDS = 10.0


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return True


def open_browser_when_ready(url: str, port: int) -> None:
    """Wait until the server accepts connections, so the tab never opens on an error page."""
    deadline = time.monotonic() + BROWSER_WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.2):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.05)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"local port (default {DEFAULT_PORT})")
    parser.add_argument(
        "--time",
        type=float,
        default=DEFAULT_THINK_SECONDS,
        help="most seconds the engine may think per move in an untimed game",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    if not 0.05 <= args.time <= 600:
        parser.error("--time must be between 0.05 and 600 seconds")

    if not (BUILD_DIR / "index.html").is_file():
        print(BUILD_HELP, file=sys.stderr)
        return 1
    if not port_is_free(args.port):
        print(f"Port {args.port} is already in use. Pick another with --port.", file=sys.stderr)
        return 1

    url = f"http://{HOST}:{args.port}"
    app = create_app(engine=SearchEngine(), port=args.port, think_seconds=args.time, static_dir=BUILD_DIR)
    print(f"chessgm is running at {url}  (Ctrl-C to stop)")
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(url, args.port), daemon=True).start()

    uvicorn.run(
        app,
        host=HOST,
        port=args.port,
        log_level="warning",
        timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
