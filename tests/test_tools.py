from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess
import pytest

from opening_book import get_book_move
from tools import bench, match

ROOT = Path(__file__).resolve().parent.parent
ENGINE = [sys.executable, str(ROOT / "uci.py")]


def test_openings_file_loads_and_is_legal() -> None:
    openings = match.load_openings()
    assert len(openings) == 60
    assert all(len(line) == 6 for line in openings)


def test_bad_openings_file_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "openings.txt"
    bad.write_text("e2e4 e7e5\ne2e5\n")
    with pytest.raises(ValueError, match="illegal move"):
        match.load_openings(bad)


def test_elo_from_score() -> None:
    assert match.elo_from_score(0.5) == pytest.approx(0.0)
    assert match.elo_from_score(0.75) == pytest.approx(190.8, abs=0.1)
    assert match.elo_from_score(1.0) is None
    assert match.elo_from_score(0.0) is None


def test_score_interval_brackets_the_score() -> None:
    low, high = match.score_interval(12, 4, 4)
    assert low < 14 / 20 < high
    assert 0.0 <= low and high <= 1.0


def test_option_and_clock_parsing() -> None:
    assert match.parse_option("UCI_Elo=1320") == ("UCI_Elo", 1320)
    assert match.parse_option("UCI_LimitStrength=true") == ("UCI_LimitStrength", True)
    assert match.parse_option("Style=solid") == ("Style", "solid")
    assert match.parse_clock("60+1") == match.Clock(60.0, 1.0)
    assert match.parse_clock("30") == match.Clock(30.0, 0.0)
    for bad in ("abc", "-5+1", "0+0"):
        with pytest.raises(argparse.ArgumentTypeError):
            match.parse_clock(bad)


def test_a_short_match_runs_end_to_end(tmp_path: Path) -> None:
    a = match.EngineSpec("a", ENGINE, {}, 0.03)
    b = match.EngineSpec("b", ENGINE, {"NullMove": False}, 0.03)
    pgn = tmp_path / "games.pgn"
    result = match.run_match(a, b, games=2, concurrency=2, pgn_path=pgn, verbose=False)
    assert result.total == 2
    assert result.wins + result.draws + result.losses == 2
    assert result.a_stats.moves > 0 and result.a_stats.depth_count > 0
    assert pgn.read_text().count("[Result ") == 2
    assert "a vs b" in match.format_summary(a, b, result)


def test_a_game_on_the_clock_does_not_flag() -> None:
    spec = match.EngineSpec("clock", ENGINE, {}, None)
    game = match.play_game(spec, spec, True, [], match.Clock(3.0, 0.05))
    assert "lost on time" not in game.reason
    assert "error" not in game.reason


def test_bench_runs_at_fixed_depth() -> None:
    results = bench.run(depth=2, seconds=1.0)
    assert len(results) == len(bench.POSITIONS)
    assert all(r.depth == 2 for r in results)


def test_bench_positions_are_valid() -> None:
    for name, fen in bench.POSITIONS:
        assert chess.Board(fen).is_valid(), name


def test_opening_book_gives_legal_moves() -> None:
    board = chess.Board()
    for _ in range(4):
        move = get_book_move(board)
        if move is None:
            break
        assert move in board.legal_moves
        board.push(move)
    assert board.move_stack, "the start position must be in the book"
