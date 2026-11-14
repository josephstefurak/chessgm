from __future__ import annotations

import random

import chess
import pytest

from engine import evaluation
from engine.evaluation import evaluate
from tests import positions as P


def random_positions(count: int, seed: int) -> list[chess.Board]:
    rng = random.Random(seed)
    boards: list[chess.Board] = []
    while len(boards) < count:
        board = chess.Board()
        for _ in range(rng.randint(2, 160)):
            if board.is_game_over():
                break
            moves = list(board.legal_moves)
            captures = [m for m in moves if board.is_capture(m)]
            board.push(rng.choice(captures if captures and rng.random() < 0.4 else moves))
        if not board.is_game_over():
            boards.append(board)
    return boards


def test_start_position_is_level() -> None:
    assert evaluate(chess.Board()) == 0


def test_colour_symmetry() -> None:
    """Swapping the colours must exactly negate the score. This is the guard against
    sign errors: the legacy evaluator added White-positive terms to a Black-positive total."""
    for board in random_positions(400, seed=3):
        assert evaluate(board) == -evaluate(board.mirror()), board.fen()


def test_material_counts() -> None:
    no_white_queen = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1")
    no_black_queen = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert evaluate(no_white_queen) < -800
    assert evaluate(no_black_queen) > 800


def test_advancing_a_passed_pawn_helps_its_owner() -> None:
    # Black keeps a knight so the endgame "unstoppable pawn" rule stays out of it.
    on_a2 = chess.Board("4k1n1/8/8/8/8/8/P7/4K1N1 w - - 0 1")
    on_a6 = chess.Board("4k1n1/8/P7/8/8/8/8/4K1N1 w - - 0 1")
    assert evaluate(on_a6) > evaluate(on_a2) + 50
    # And the mirror image for Black.
    assert evaluate(on_a6.mirror()) < evaluate(on_a2.mirror()) - 50


def test_unstoppable_pawn_is_winning_for_its_owner() -> None:
    # The legacy evaluator scored this position as -395 for White.
    assert evaluate(chess.Board(P.UNSTOPPABLE_PAWN)) > 400


def test_rook_prefers_open_file() -> None:
    closed = chess.Board("4k3/pppp1ppp/8/8/8/8/PPPP1PPP/R3K3 w - - 0 1")
    opened = chess.Board("4k3/pppp1ppp/8/8/8/8/PPPP1PPP/4RK2 w - - 0 1")
    assert evaluate(opened) > evaluate(closed)


def test_doubled_and_isolated_pawns_are_penalised() -> None:
    healthy = chess.Board("4k3/8/8/8/8/8/PP6/4K3 w - - 0 1")
    doubled = chess.Board("4k3/8/8/8/8/P7/P7/4K3 w - - 0 1")
    assert evaluate(doubled) < evaluate(healthy)


def test_opposition_goes_to_the_side_not_to_move() -> None:
    black_to_move = chess.Board("8/8/4k3/8/4K3/8/8/8 b - - 0 1")
    white_to_move = chess.Board("8/8/4k3/8/4K3/8/8/8 w - - 0 1")
    assert evaluate(black_to_move) > 0  # White holds the opposition
    assert evaluate(white_to_move) < 0  # Black holds it


def test_lone_king_is_driven_to_the_edge() -> None:
    centre = chess.Board("8/8/8/4k3/8/8/8/R3K3 w - - 0 1")
    corner = chess.Board("7k/8/8/8/8/8/8/R3K3 w - - 0 1")
    assert evaluate(corner) > evaluate(centre)


def test_pawn_cache_does_not_change_results() -> None:
    boards = random_positions(50, seed=9)
    evaluation.clear_caches()
    cold = [evaluate(b) for b in boards]
    warm = [evaluate(b) for b in boards]
    assert cold == warm


@pytest.mark.parametrize("fen", [P.MANY_CAPTURES, P.QUEEN_UP, P.PERPETUAL_CHECK])
def test_evaluate_does_not_modify_the_board(fen: str) -> None:
    board = chess.Board(fen)
    evaluate(board)
    assert board.fen() == fen
