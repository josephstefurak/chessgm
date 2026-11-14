"""The terminal front end: move parsing, board drawing, result text."""

from __future__ import annotations

import builtins

import chess
import pytest

import main
from tests import positions as P


def test_parse_move_accepts_san_and_uci() -> None:
    board = chess.Board()
    assert main.parse_move(board, "Nf3") == chess.Move.from_uci("g1f3")
    assert main.parse_move(board, "g1f3") == chess.Move.from_uci("g1f3")
    assert main.parse_move(board, "  e4 ") == chess.Move.from_uci("e2e4")
    assert main.parse_move(board, "E2E4") == chess.Move.from_uci("e2e4")


@pytest.mark.parametrize("text", ["", "e2e5", "Ke2", "hello", "x" * 500, "e2e4; rm -rf /"])
def test_parse_move_rejects_bad_input(text: str) -> None:
    with pytest.raises(ValueError):
        main.parse_move(chess.Board(), text)


def test_board_is_drawn_from_the_players_side() -> None:
    white = main.render(chess.Board(), chess.WHITE).splitlines()
    black = main.render(chess.Board(), chess.BLACK).splitlines()
    assert white[1].split() == ["8", *"rnbqkbnr"]
    assert white[-1].split() == list("abcdefgh")
    assert black[1].split() == ["1", *"RNBKQBNR"]
    assert black[-1].split() == list("hgfedcba")


def test_result_text() -> None:
    assert main.describe_result(chess.Board(P.CHECKMATED)) == "White wins by checkmate."
    assert main.describe_result(chess.Board(P.STALEMATED)) == "Draw (stalemate)."
    assert main.describe_result(chess.Board()) == "Game not finished."


def test_engine_move_uses_book_then_search() -> None:
    from engine.search import Searcher

    move, note = main.engine_move(chess.Board(), Searcher(), 0.2)
    assert note == "opening book"
    board = chess.Board(P.MATE_IN_1_WHITE)
    move, note = main.engine_move(board, Searcher(), 0.2)
    assert move == chess.Move.from_uci("h5f7")
    assert "mate in 1 for White" in note


def test_a_whole_session_from_typed_input(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Human is White in a mate-in-1 position: a bad move, help, then the mating move."""
    typed = iter(["zzz", "help", "Qxf7#"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(typed))
    assert main.main(["--color", "w", "--fen", P.MATE_IN_1_WHITE]) == 0
    out = capsys.readouterr().out
    assert "'zzz' is not a legal move here." in out
    assert "White wins by checkmate." in out


def test_engine_replies_and_quit_works(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    typed = iter(["e4", "undo", "d4", "quit"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(typed))
    assert main.main(["--color", "w", "--time", "0.1"]) == 0
    out = capsys.readouterr().out
    assert out.count("Engine plays") == 2
    assert "Goodbye." in out


def test_closed_input_exits_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def closed(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", closed)
    assert main.main([]) == 0
    assert "Goodbye." in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["--time", "0"], ["--time", "9999"], ["--fen", "not a fen"], ["--color", "x"]])
def test_bad_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        main.main(argv)
