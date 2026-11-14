"""gui.py: argument checks and the two refusals to start."""

from __future__ import annotations

import socket
from pathlib import Path

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
