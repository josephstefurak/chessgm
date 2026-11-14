"""gui.py: argument checks and the two refusals to start."""

from __future__ import annotations

import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2 as httpx
import pytest

import gui


@pytest.mark.parametrize(
    "argv",
    [
        ["--port", "80"],
        ["--port", "70000"],
        ["--port", "abc"],
        ["--time", "0"],
        ["--time", "9999"],
        ["--bogus"],
    ],
)
def test_bad_arguments_are_refused(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        gui.main(argv)
    assert caught.value.code == 2


def test_refuses_to_start_without_a_built_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gui, "BUILD_DIR", tmp_path / "dist")
    assert gui.main(["--no-browser"]) == 1
    message = capsys.readouterr().err
    assert "npm run build" in message and "npm install" in message


def test_refuses_a_port_that_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(gui, "BUILD_DIR", tmp_path)
    with socket.socket() as taken:
        taken.bind((gui.HOST, 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert gui.port_is_free(port) is False
        assert gui.main(["--port", str(port), "--no-browser"]) == 1
    assert "already in use" in capsys.readouterr().err


def test_the_server_only_ever_binds_to_loopback() -> None:
    assert gui.HOST == "127.0.0.1"


RUN_LAUNCHER = """
import pathlib, sys
import gui
gui.BUILD_DIR = pathlib.Path(sys.argv[1])
sys.exit(gui.main(["--port", sys.argv[2], "--no-browser"]))
"""


def test_ctrl_c_with_the_page_open_exits_quietly(tmp_path: Path) -> None:
    """The launcher as a real process, stopped the way a person stops it. An open
    event stream used to turn this into an error and a traceback."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html>")
    with socket.socket() as probe:
        probe.bind((gui.HOST, 0))
        port = probe.getsockname()[1]

    launcher = subprocess.Popen(
        [sys.executable, "-c", RUN_LAUNCHER, str(tmp_path), str(port)],
        cwd=Path(gui.__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = f"http://{gui.HOST}:{port}"
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection((gui.HOST, port), timeout=0.2):
                    break
            except OSError:
                assert launcher.poll() is None, launcher.stderr.read() if launcher.stderr else ""
                assert time.monotonic() < deadline, "the launcher did not start"
                time.sleep(0.05)

        with httpx.Client(base_url=url, timeout=10) as client, client.stream("GET", "/api/events") as page:
            lines = page.iter_lines()
            assert next(lines) == "event: state"
            launcher.send_signal(signal.SIGINT)
            for _ in lines:
                pass
        out, err = launcher.communicate(timeout=10)
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.communicate()

    assert launcher.returncode == 0
    assert err == ""
    assert out.strip() == f"chessgm is running at {url}  (Ctrl-C to stop)"
