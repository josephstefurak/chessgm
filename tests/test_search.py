from __future__ import annotations

import threading
import time
from dataclasses import fields

import chess
import pytest

from engine.search import MATE, Limits, SearchConfig, Searcher, SearchInfo, mate_in_moves
from tests import positions as P


@pytest.mark.parametrize(
    ("fen", "moves"),
    [(P.MATE_IN_1_WHITE, 1), (P.MATE_IN_1_BLACK, 1), (P.MATE_IN_2, 2), (P.MATE_IN_3, 3)],
)
def test_finds_forced_mate_with_correct_distance(fen: str, moves: int) -> None:
    board = chess.Board(fen)
    result = Searcher().search(board, Limits(depth=8))
    assert result.mate_in == moves
    assert result.move in board.legal_moves


def test_mate_in_one_is_played_immediately() -> None:
    board = chess.Board(P.MATE_IN_1_WHITE)
    result = Searcher().search(board, Limits(depth=6))
    board.push(result.move)
    assert board.is_checkmate()


def test_only_mate_in_three_move_is_found() -> None:
    board = chess.Board(P.MATE_IN_3)
    assert Searcher().search(board, Limits(depth=8)).move == chess.Move.from_uci("a2g2")


def test_being_mated_is_reported_as_negative_mate() -> None:
    result = Searcher().search(chess.Board(P.MATED_IN_1_SINGLE_REPLY), Limits(depth=4))
    assert result.mate_in == -1


def test_mate_score_helpers() -> None:
    assert mate_in_moves(MATE - 1) == 1
    assert mate_in_moves(MATE - 3) == 2
    assert mate_in_moves(-(MATE - 2)) == -1
    assert mate_in_moves(250) is None


def test_plain_alpha_beta_still_finds_mate() -> None:
    """With every pruning technique switched off the answer must not change."""
    off = SearchConfig(**{f.name: False for f in fields(SearchConfig)})
    result = Searcher(off).search(chess.Board(P.MATE_IN_2), Limits(depth=5))
    assert result.mate_in == 2


def test_avoids_stalemate_when_winning() -> None:
    board = chess.Board(P.STALEMATE_TRAP)
    result = Searcher().search(board, Limits(depth=6))
    board.push(result.move)
    assert not board.is_stalemate()
    assert result.mate_in == 2


def test_fifty_move_rule_is_a_draw() -> None:
    result = Searcher().search(chess.Board(P.FIFTY_MOVE_DRAW), Limits(depth=6))
    assert result.score == 0


def test_mate_beats_the_fifty_move_rule() -> None:
    result = Searcher().search(chess.Board(P.FIFTY_MOVE_MATE_FIRST), Limits(depth=4))
    assert result.mate_in == 1


def test_losing_side_takes_perpetual_check() -> None:
    board = chess.Board(P.PERPETUAL_CHECK)
    result = Searcher().search(board, Limits(depth=8))
    assert result.move == chess.Move.from_uci("d1d8")
    assert result.score == 0


def test_losing_side_repeats_a_position_from_the_game() -> None:
    """The repetition is with a position played before the search started."""
    board = chess.Board(P.QUEEN_UP)
    for uci in ("g1h1", "g8h8", "h1g1"):
        board.push_uci(uci)
    result = Searcher().search(board, Limits(depth=5))
    assert result.move == chess.Move.from_uci("h8g8")
    assert result.score == 0


def test_winning_side_does_not_repeat() -> None:
    board = chess.Board(P.QUEEN_UP)
    for uci in ("g1h1", "g8h8", "h1g1", "h8g8"):
        board.push_uci(uci)
    result = Searcher().search(board, Limits(depth=5))
    assert result.score > 500
    board.push(result.move)
    assert not board.is_repetition(2)


def test_wins_a_hanging_queen() -> None:
    result = Searcher().search(chess.Board(P.HANGING_QUEEN), Limits(depth=4))
    assert result.move == chess.Move.from_uci("f3g5")


@pytest.mark.parametrize("budget", [0.0005, 0.005, 0.05])
def test_tiny_time_budget_still_returns_a_searched_legal_move(budget: float) -> None:
    """The legacy engine returned an arbitrary first legal move here."""
    board = chess.Board(P.MANY_CAPTURES)
    started = time.perf_counter()
    result = Searcher().search(board, Limits(soft_time=budget, hard_time=budget))
    assert result.move in board.legal_moves
    assert result.depth >= 1  # at least one full depth was searched
    assert time.perf_counter() - started < 0.5


def test_hard_time_limit_is_respected() -> None:
    board = chess.Board(P.MANY_CAPTURES)
    started = time.perf_counter()
    Searcher().search(board, Limits(hard_time=0.3))
    assert time.perf_counter() - started < 0.3 + 0.15


def test_single_legal_move_is_played_without_using_the_clock() -> None:
    board = chess.Board(P.MATED_IN_1_SINGLE_REPLY)
    started = time.perf_counter()
    result = Searcher().search(board, Limits(soft_time=5.0, hard_time=5.0))
    assert time.perf_counter() - started < 0.2
    assert result.move == chess.Move.from_uci("h8g8")


def test_depth_limit_is_respected() -> None:
    result = Searcher().search(chess.Board(), Limits(depth=3))
    assert result.depth == 3


def test_node_limit_stops_the_search() -> None:
    result = Searcher().search(chess.Board(P.MANY_CAPTURES), Limits(nodes=5_000))
    assert result.nodes < 5_000 + 5_000  # depth 1 is uninterruptible, then checked every 256 nodes


def test_board_is_restored_after_search_and_after_abort() -> None:
    board = chess.Board(P.MANY_CAPTURES)
    board.push_uci("e1g1")
    fen, stack = board.fen(), list(board.move_stack)
    Searcher().search(board, Limits(depth=3))
    assert (board.fen(), board.move_stack) == (fen, stack)
    Searcher().search(board, Limits(hard_time=0.05))
    assert (board.fen(), board.move_stack) == (fen, stack)


def test_stop_from_another_thread() -> None:
    board = chess.Board()
    searcher = Searcher()
    results: list[object] = []
    thread = threading.Thread(target=lambda: results.append(searcher.search(board, Limits())))
    thread.start()
    time.sleep(0.2)
    searcher.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert len(results) == 1


def test_game_over_position_raises() -> None:
    for fen in (P.STALEMATED, P.CHECKMATED):
        with pytest.raises(ValueError):
            Searcher().search(chess.Board(fen), Limits(depth=2))


def test_fixed_depth_search_is_deterministic() -> None:
    first = Searcher().search(chess.Board(P.MANY_CAPTURES), Limits(depth=4))
    second = Searcher().search(chess.Board(P.MANY_CAPTURES), Limits(depth=4))
    assert (first.move, first.score, first.nodes) == (second.move, second.score, second.nodes)


def test_mate_is_still_found_with_a_warm_transposition_table() -> None:
    """Mate scores are stored relative to the node; reusing them must keep the distance right."""
    searcher = Searcher()
    board = chess.Board(P.MATE_IN_3)
    assert searcher.search(board, Limits(depth=8)).mate_in == 3
    assert searcher.search(board, Limits(depth=8)).mate_in == 3
    board.push_uci("a2g2")
    board.push(next(iter(board.legal_moves)))
    assert searcher.search(board, Limits(depth=8)).mate_in == 2


def test_info_callback_reports_each_depth_in_order() -> None:
    seen: list[SearchInfo] = []
    Searcher().search(chess.Board(), Limits(depth=4), seen.append)
    assert [info.depth for info in seen] == [1, 2, 3, 4]
    assert all(info.pv and info.nodes > 0 for info in seen)
    # The reported line must be playable from the root.
    board = chess.Board()
    for move in seen[-1].pv:
        assert move in board.legal_moves
        board.push(move)
