"""The UCI front end, tested both in-process and as a real subprocess."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import chess
import pytest

from tests import positions as P
from uci import UciEngine

ROOT = Path(__file__).resolve().parent.parent
BOOK_FIRST_MOVES = {"e2e4", "d2d4", "g1f3", "c2c4"}


class Session:
    """A running `python uci.py` we can talk to line by line."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "uci.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(ROOT),
        )

    def send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def read_until(self, prefix: str, timeout: float = 10.0) -> list[str]:
        assert self.proc.stdout is not None
        lines: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))
            if lines[-1].startswith(prefix):
                return lines
        raise AssertionError(f"never saw a line starting with {prefix!r}; got {lines}")

    def close(self) -> tuple[int, str]:
        assert self.proc.stdin is not None and self.proc.stderr is not None
        self.proc.stdin.close()
        code = self.proc.wait(timeout=5)
        return code, self.proc.stderr.read()


@pytest.fixture
def session() -> Session:
    return Session()


def bestmove(lines: list[str]) -> str:
    return lines[-1].split()[1]


def test_handshake_prints_only_uci(session: Session) -> None:
    session.send("uci")
    lines = session.read_until("uciok")
    assert all(line.startswith(("id ", "option ", "uciok")) for line in lines), lines
    session.send("isready")
    assert session.read_until("readyok") == ["readyok"]
    code, stderr = session.close()
    assert code == 0
    assert stderr == ""


def test_closing_stdin_ends_the_process_even_mid_search(session: Session) -> None:
    """The legacy wrapper spun at 99% CPU forever when stdin closed."""
    session.send("position startpos")
    session.send("go infinite")
    session.read_until("info depth")
    code, _ = session.close()
    assert code == 0


def test_go_movetime_returns_a_legal_move_on_time(session: Session) -> None:
    session.send(f"position fen {P.MANY_CAPTURES}")
    started = time.monotonic()
    session.send("go movetime 300")
    lines = session.read_until("bestmove")
    assert time.monotonic() - started < 1.0
    assert chess.Move.from_uci(bestmove(lines)) in chess.Board(P.MANY_CAPTURES).legal_moves
    assert any(line.startswith("info depth") and " pv " in line for line in lines)
    session.close()


def test_stop_ends_an_infinite_search(session: Session) -> None:
    session.send("position startpos moves e2e4")
    session.send("go infinite")
    session.read_until("info depth")
    session.send("stop")
    lines = session.read_until("bestmove", timeout=3.0)
    board = chess.Board()
    board.push_uci("e2e4")
    assert chess.Move.from_uci(bestmove(lines)) in board.legal_moves
    session.close()


def test_isready_is_answered_while_thinking(session: Session) -> None:
    session.send("position startpos")
    session.send("go infinite")
    session.send("isready")
    session.read_until("readyok", timeout=3.0)
    session.send("quit")
    assert session.proc.wait(timeout=5) == 0


def test_malformed_input_never_kills_the_engine(session: Session) -> None:
    for line in (
        "position fen this is not a fen",
        "position startpos moves e2e5",
        "position",
        "setoption name Hash value banana",
        "setoption name NoSuchOption value 1",
        "setoption",
        "completely unknown command",
        "x" * 70_000,
        "",
    ):
        session.send(line)
    session.send("go depth nonsense")  # falls back to a short think and still answers
    session.read_until("bestmove", timeout=5.0)
    session.send("position startpos moves e2e4 e7e5")
    session.send("go depth 2")
    lines = session.read_until("bestmove")
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("e7e5")
    assert chess.Move.from_uci(bestmove(lines)) in board.legal_moves
    code, stderr = session.close()
    assert code == 0
    assert stderr == ""


def test_bad_position_command_keeps_the_previous_position(session: Session) -> None:
    session.send(f"position fen {P.MATE_IN_1_WHITE}")
    session.send("position fen 8/8/8/8/8/8/8/8 w - - 0 1")  # no kings: rejected
    session.send("go depth 3")
    assert bestmove(session.read_until("bestmove")) == "h5f7"
    session.close()


def test_mate_is_reported_as_mate(session: Session) -> None:
    session.send(f"position fen {P.MATE_IN_2}")
    session.send("go depth 6")
    lines = session.read_until("bestmove")
    assert any("score mate 2" in line for line in lines)
    session.close()


@pytest.mark.parametrize("fen", [P.STALEMATED, P.CHECKMATED])
def test_game_over_position_answers_with_null_move(session: Session, fen: str) -> None:
    session.send(f"position fen {fen}")
    session.send("go movetime 100")
    assert session.read_until("bestmove") == ["bestmove 0000"]
    session.close()


def test_opening_book_is_used_on_the_clock_and_can_be_switched_off(session: Session) -> None:
    session.send("position startpos")
    session.send("go wtime 60000 btime 60000")
    lines = session.read_until("bestmove")
    assert lines == [lines[-1]], "a book move needs no search output"
    assert bestmove(lines) in BOOK_FIRST_MOVES

    session.send("setoption name OwnBook value false")
    session.send("go wtime 2000 btime 2000")
    assert any(line.startswith("info depth") for line in session.read_until("bestmove"))
    session.close()


def test_clock_search_uses_a_fraction_of_the_clock(session: Session) -> None:
    session.send("setoption name OwnBook value false")
    session.send("position startpos")
    started = time.monotonic()
    session.send("go wtime 10000 btime 10000 winc 100 binc 100")
    session.read_until("bestmove")
    assert time.monotonic() - started < 2.0
    session.close()


# ------------------------------------------------------------- in-process


def make_engine() -> tuple[UciEngine, list[str]]:
    out: list[str] = []
    return UciEngine(out.append), out


def test_search_toggles_reach_the_searcher() -> None:
    engine, out = make_engine()
    engine.handle("setoption name NullMove value false")
    engine.handle("setoption name LMR value false")
    assert engine.searcher.config.null_move is False
    assert engine.searcher.config.late_move_reductions is False
    assert engine.searcher.config.futility is True
    assert out == []


def test_option_names_are_case_insensitive_and_may_contain_spaces() -> None:
    engine, _ = make_engine()
    engine.handle("setoption name move overhead value 250")
    assert engine.move_overhead_ms == 250


def test_out_of_range_option_is_rejected() -> None:
    engine, out = make_engine()
    engine.handle("setoption name Move Overhead value 999999")
    assert engine.move_overhead_ms == 30
    assert out and out[0].startswith("info string ignored")


def test_position_with_moves_is_applied() -> None:
    engine, _ = make_engine()
    engine.handle("position startpos moves e2e4 c7c5 g1f3")
    assert engine.board.fen().startswith("rnbqkbnr/pp1ppppp/8/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R b")
    assert len(engine.board.move_stack) == 3  # history is kept, so repetitions can be seen


def test_quit_returns_false() -> None:
    engine, _ = make_engine()
    assert engine.handle("isready") is True
    assert engine.handle("quit") is False
