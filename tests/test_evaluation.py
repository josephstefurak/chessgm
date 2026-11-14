from __future__ import annotations

import random

import chess
import pytest

from engine import evaluation
from engine import weights as W
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


def test_start_position_is_level_apart_from_the_move() -> None:
    board = chess.Board()
    assert evaluate(board) == W.TEMPO
    board.push(chess.Move.null())
    assert evaluate(board) == -W.TEMPO


@pytest.mark.parametrize(("mg", "eg"), [(0, 0), (5, -3), (-5, 3), (-120, -77), (3000, -2500), (-1, 0), (0, -1)])
def test_packed_scores_round_trip(mg: int, eg: int) -> None:
    packed = evaluation._pack(mg, eg)
    assert evaluation._unpack(packed) == (mg, eg)
    assert evaluation._unpack(-packed) == (-mg, -eg)
    assert evaluation._unpack(packed + evaluation._pack(7, -9)) == (mg + 7, eg - 9)


def test_blend_is_symmetric_and_hits_both_ends() -> None:
    assert evaluation._blend(100, 40, W.PHASE_MAX) == 100
    assert evaluation._blend(100, 40, 0) == 40
    for mg, eg, phase in [(7, -3, 5), (-7, 3, 5), (1, 0, 1), (-1, 0, 1)]:
        assert evaluation._blend(mg, eg, phase) == -evaluation._blend(-mg, -eg, phase)


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


def test_rook_file_bonuses() -> None:
    def rook_term(fen: str) -> tuple[int, int]:
        board = chess.Board(fen)
        white, black = board.occupied_co[chess.WHITE], board.occupied_co[chess.BLACK]
        return evaluation._unpack(
            evaluation._rooks(board.rooks & white, board.rooks & black, board.pawns & white, board.pawns & black)
        )

    closed = rook_term("6k1/pppp1ppp/8/8/8/8/PPPP1PPP/R5K1 w - - 0 1")
    half_open = rook_term("6k1/pppppppp/8/8/8/8/PPPP1PPP/4R1K1 w - - 0 1")
    fully_open = rook_term("6k1/pppp1ppp/8/8/8/8/PPPP1PPP/4R1K1 w - - 0 1")
    assert closed == (0, 0)
    assert half_open == (W.ROOK_SEMI_OPEN_FILE_MG, W.ROOK_SEMI_OPEN_FILE_EG)
    assert fully_open == (W.ROOK_OPEN_FILE_MG, W.ROOK_OPEN_FILE_EG)


def test_bishop_pair_is_worth_more_than_bishop_and_knight() -> None:
    pair = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/2B1KB2 w - - 0 1")
    mixed = chess.Board("4k3/pppppppp/8/8/8/8/PPPPPPPP/2B1K1N1 w - - 0 1")
    assert evaluate(pair) > evaluate(mixed)


def test_king_shelter() -> None:
    white_pawns = chess.Board("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1").pawns
    assert evaluation._king_shelter(chess.G1, chess.WHITE, white_pawns) == 3 * W.PAWN_SHIELD_NEAR
    assert evaluation._king_shelter(chess.G1, chess.WHITE, 0) == -3 * W.KING_OPEN_FILE_PENALTY
    assert evaluation._king_shelter(chess.E4, chess.WHITE, white_pawns) == 0  # king has left home
    black_pawns = chess.Board("6k1/5ppp/8/8/8/8/8/6K1 w - - 0 1").pawns
    assert evaluation._king_shelter(chess.G8, chess.BLACK, black_pawns) == 3 * W.PAWN_SHIELD_NEAR


def test_pawnless_small_edge_is_scaled_toward_a_draw() -> None:
    rook_vs_bishop = chess.Board("4k3/8/3b4/8/8/8/8/R3K3 w - - 0 1")
    rook_vs_nothing = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    assert 0 < evaluate(rook_vs_bishop) < 100
    assert evaluate(rook_vs_nothing) > 400


def test_blocked_or_catchable_pawn_is_not_called_unstoppable() -> None:
    catchable = chess.Board("8/8/2k5/8/P7/8/8/K7 b - - 0 1")  # king steps into the square
    blocked = chess.Board("8/K7/P7/8/8/8/8/7k b - - 0 1")
    free = chess.Board(P.UNSTOPPABLE_PAWN)
    assert evaluate(free) > evaluate(catchable) + 300
    assert evaluate(free) > evaluate(blocked) + 300


def test_doubled_and_isolated_pawns_are_penalised() -> None:
    healthy = chess.Board("4k3/8/8/8/8/8/PP6/4K3 w - - 0 1")
    doubled = chess.Board("4k3/8/8/8/8/P7/P7/4K3 w - - 0 1")
    assert evaluate(doubled) < evaluate(healthy)


def test_opposition_goes_to_the_side_not_to_move() -> None:
    # A pawn ending with the kings facing each other. Having to move loses the opposition,
    # and that outweighs the small bonus for having the move.
    black_to_move = chess.Board("8/p7/4k3/8/4K3/8/P7/8 b - - 0 1")
    white_to_move = chess.Board("8/p7/4k3/8/4K3/8/P7/8 w - - 0 1")
    assert evaluate(black_to_move) - evaluate(white_to_move) == 2 * (W.OPPOSITION_BONUS - W.TEMPO)


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

