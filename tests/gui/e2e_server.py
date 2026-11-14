"""The real GUI server with a scripted engine, for the browser tests.

    python -m tests.gui.e2e_server --port 8791

Everything is the shipped code except the engine, which answers at once with a
move that depends only on the position (see `fakes.ScriptedEngine`), and one extra
time control short enough to watch a flag fall. The shipped launcher, gui.py,
has no test switches; the one browser test that needs the real engine runs it as is.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tests.gui.fakes import ScriptedEngine
from webgui.server.app import create_app
from webgui.server.clock import PRESETS, TimeControl
from webgui.server.runner import serve

BUILD_DIR = Path(__file__).resolve().parents[2] / "webgui" / "web" / "dist"
# Id "0+1": four seconds each and one second a move. Only this test server offers it.
FLAG_FALL_CONTROL = TimeControl("0+1", 4, 1)
ENGINE_DELAY_SECONDS = 0.15  # long enough for the browser to show "Thinking"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)
    if not (BUILD_DIR / "index.html").is_file():
        print(f"No built UI in {BUILD_DIR}. Run `npm run build` in webgui/web first.", file=sys.stderr)
        return 1
    app = create_app(
        engine=ScriptedEngine(delay=ENGINE_DELAY_SECONDS),
        port=args.port,
        think_seconds=0.1,
        static_dir=BUILD_DIR,
        time_controls=(*PRESETS, FLAG_FALL_CONTROL),
    )
    serve(app, host="127.0.0.1", port=args.port, grace_seconds=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
