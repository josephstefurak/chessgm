"""The real engine behind the GUI: it answers, and a cancelled search stops promptly."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

import chess
import pytest

from engine.search import Limits, Searcher, SearchInfo, SearchResult
from tests import positions as P
from webgui.server.engine_port import EngineMove, SearchEngine

LONG = Limits(soft_time=30.0, hard_time=30.0)  # far longer than any test may take
PROMPT_SECONDS = 2.0


class Collected:
    """What an engine request reported, with events to wait on."""

    def __init__(self) -> None:
        self.infos: list[SearchInfo] = []
        self.moves: list[EngineMove] = []
        self.errors: list[Exception] = []
        self.first_info = threading.Event()
        self.done = threading.Event()

    def on_info(self, info: SearchInfo) -> None:
        self.infos.append(info)
        self.first_info.set()

    def on_done(self, answer: EngineMove) -> None:
        self.moves.append(answer)
        self.done.set()

    def on_error(self, error: Exception) -> None:
        self.errors.append(error)
        self.done.set()

    def ask(self, engine: SearchEngine, fen: str, limits: Limits) -> Collected:
        engine.request_move(chess.Board(fen), limits, self.on_info, self.on_done, self.on_error)
        return self


@pytest.fixture
def engine() -> Iterator[SearchEngine]:
    search_engine = SearchEngine()
    yield search_engine
    search_engine.close()


def test_a_book_position_is_answered_from_the_book(engine: SearchEngine) -> None:
    got = Collected().ask(engine, chess.STARTING_FEN, LONG)
    assert got.done.wait(PROMPT_SECONDS)
    (answer,) = got.moves
    assert (answer.source, answer.info) == ("book", None)
    assert answer.move in chess.Board().legal_moves
    assert got.infos == [] and got.errors == []


def test_a_search_reports_progress_and_a_final_result(engine: SearchEngine) -> None:
    got = Collected().ask(engine, P.HANGING_QUEEN, Limits(depth=3))
    assert got.done.wait(10)
    (answer,) = got.moves
    assert answer.source == "search" and answer.move == chess.Move.from_uci("f3g5")
    assert answer.info is not None and answer.info.depth == 3
    assert [info.depth for info in got.infos] == [1, 2, 3]
    assert got.errors == []


def test_the_callers_board_is_left_alone(engine: SearchEngine) -> None:
    board = chess.Board(P.MANY_CAPTURES)
    before = board.fen()
    got = Collected()
    engine.request_move(board, Limits(depth=2), got.on_info, got.on_done, got.on_error)
    assert got.done.wait(10)
    assert board.fen() == before and not board.move_stack


def test_cancel_stops_a_long_search_and_it_never_answers(engine: SearchEngine) -> None:
    long = Collected().ask(engine, P.MANY_CAPTURES, LONG)
    assert long.first_info.wait(10)
    started = time.monotonic()
    engine.cancel()
    quick = Collected().ask(engine, P.HANGING_QUEEN, Limits(depth=1))
    assert quick.done.wait(PROMPT_SECONDS), "the worker was still busy with the cancelled search"
    assert time.monotonic() - started < PROMPT_SECONDS
    assert long.moves == [] and long.errors == []


def test_a_new_request_replaces_the_one_in_progress(engine: SearchEngine) -> None:
    long = Collected().ask(engine, P.MANY_CAPTURES, LONG)
    assert long.first_info.wait(10)
    quick = Collected().ask(engine, P.HANGING_QUEEN, Limits(depth=1))
    assert quick.done.wait(PROMPT_SECONDS)
    assert long.moves == []


class StopLostOnEntry(Searcher):
    """A searcher that is cancelled in the instant before its search begins.

    `Searcher.search` clears the stop flag as its first act, so this stop is erased.
    That is the race a takeback can hit; here it happens every time.
    """

    def __init__(self) -> None:
        super().__init__()
        self.before_search: Callable[[], None] = lambda: None
        self.returned = threading.Event()

    def search(
        self, board: chess.Board, limits: Limits, on_info: Callable[[SearchInfo], None] | None = None
    ) -> SearchResult:
        self.before_search()
        try:
            return super().search(board, limits, on_info)
        finally:
            self.returned.set()


def test_a_cancel_that_lands_just_before_the_search_starts_is_not_lost() -> None:
    searcher = StopLostOnEntry()
    engine = SearchEngine(searcher)
    try:
        searcher.before_search = engine.cancel
        lost = Collected().ask(engine, P.MANY_CAPTURES, LONG)
        # Nothing else is asked of the engine, as after a takeback: it must stop by itself.
        assert searcher.returned.wait(PROMPT_SECONDS), "the erased stop left a 30 second search running"
        assert lost.moves == [] and lost.infos == [] and lost.errors == []
    finally:
        engine.close()


def test_a_failing_search_is_reported_not_swallowed() -> None:
    class Broken(Searcher):
        def search(
            self, board: chess.Board, limits: Limits, on_info: Callable[[SearchInfo], None] | None = None
        ) -> SearchResult:
            raise RuntimeError("boom")

    engine = SearchEngine(Broken())
    try:
        got = Collected().ask(engine, P.HANGING_QUEEN, Limits(depth=1))
        assert got.done.wait(PROMPT_SECONDS)
        assert got.moves == [] and [type(error) for error in got.errors] == [RuntimeError]
        again = Collected().ask(engine, chess.STARTING_FEN, LONG)  # the worker survived
        assert again.done.wait(PROMPT_SECONDS) and len(again.moves) == 1
    finally:
        engine.close()


def test_new_game_clears_what_the_engine_remembers() -> None:
    searcher = Searcher()
    engine = SearchEngine(searcher)
    try:
        got = Collected().ask(engine, P.HANGING_QUEEN, Limits(depth=3))
        assert got.done.wait(10)
        assert searcher.tt
        engine.new_game()
        after = Collected().ask(engine, chess.STARTING_FEN, LONG)  # runs after the reset job
        assert after.done.wait(PROMPT_SECONDS)
        assert not searcher.tt
    finally:
        engine.close()
