"""Stand-ins for the engine and the clock, so GUI tests are instant and exact."""

from __future__ import annotations

import datetime as dt
import random
import threading
from dataclasses import dataclass

import chess

from engine.search import Limits, SearchInfo
from webgui.server.engine_port import EngineMove, OnDone, OnError, OnInfo
from webgui.server.session import GameSession

FIXED_DATE = dt.date(2026, 11, 13)


class FakeTime:
    def __init__(self) -> None:
        self.value = 1000.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass(frozen=True)
class Request:
    board: chess.Board
    limits: Limits
    on_info: OnInfo
    on_done: OnDone
    on_error: OnError

    def reply(self, uci: str, info: SearchInfo | None = None) -> None:
        source = "book" if info is None else "search"
        self.on_done(EngineMove(chess.Move.from_uci(uci), source, info))  # type: ignore[arg-type]


class ManualEngine:
    """An engine that answers only when the test tells it to."""

    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.pending: Request | None = None
        self.cancels = 0
        self.new_games = 0
        self.closed = False

    def request_move(
        self, board: chess.Board, limits: Limits, on_info: OnInfo, on_done: OnDone, on_error: OnError
    ) -> None:
        self.pending = Request(board, limits, on_info, on_done, on_error)
        self.requests.append(self.pending)

    def cancel(self) -> None:
        self.cancels += 1
        self.pending = None

    def new_game(self) -> None:
        self.new_games += 1
        self.pending = None

    def close(self) -> None:
        self.closed = True

    def reply(self, uci: str, info: SearchInfo | None = None) -> None:
        assert self.pending is not None, "the engine was not asked for a move"
        request, self.pending = self.pending, None
        request.reply(uci, info)


# What the scripted engine prefers to play, in order, when the move is legal.
# Chosen so that short human lines reach a promotion (1.h4 g5 2.hxg5 h6 3.gxh6 a6
# 4.h7 a5 5.hxg8=Q) and a checkmate (1.e4 g5 2.Qh5 h6 3.Bc4 a6 4.Qxf7#).
SCRIPT = ("g7g5", "h7h6", "a7a6", "a6a5", "a5a4", "e2e4", "d2d4", "g1f3", "b1c3")
SCRIPTED_INFO_DEPTH = 5
SCRIPTED_INFO_SCORE = 34  # centipawns for the side to move


class ScriptedEngine:
    """Answers at once, on another thread, with a move that depends only on the position."""

    def __init__(self, delay: float = 0.05) -> None:
        self._delay = delay
        self._lock = threading.Lock()
        self._current = 0

    def request_move(
        self, board: chess.Board, limits: Limits, on_info: OnInfo, on_done: OnDone, on_error: OnError
    ) -> None:
        with self._lock:
            self._current += 1
            number = self._current

        def answer() -> None:
            move = choose(board)
            info = SearchInfo(SCRIPTED_INFO_DEPTH, SCRIPTED_INFO_SCORE, 1000, self._delay, [move])
            with self._lock:
                stale = number != self._current
            if not stale:
                on_info(info)
                on_done(EngineMove(move, "search", info))

        timer = threading.Timer(self._delay, answer)
        timer.daemon = True
        timer.start()

    def cancel(self) -> None:
        with self._lock:
            self._current += 1

    def new_game(self) -> None:
        self.cancel()

    def close(self) -> None:
        self.cancel()


def choose(board: chess.Board) -> chess.Move:
    legal = sorted(board.legal_moves, key=lambda move: move.uci())
    for uci in SCRIPT:
        move = chess.Move.from_uci(uci)
        if move in legal:
            return move
    return legal[0]


def make_session(
    human: str = "white", time_control: str | None = None, think_seconds: float = 2.0
) -> tuple[GameSession, ManualEngine, FakeTime]:
    """A session with a manual engine, a fake clock and no background timer."""
    engine = ManualEngine()
    clock = FakeTime()
    session = GameSession(
        engine,
        think_seconds=think_seconds,
        now=clock.now,
        schedule=None,
        today=lambda: FIXED_DATE,
        rng=random.Random(0),
    )
    if human != "white" or time_control is not None:
        session.new_game(human, time_control)  # type: ignore[arg-type]
    return session, engine, clock


def play(session: GameSession, engine: ManualEngine, line: str) -> None:
    """Play a line of UCI moves, the human's through the session and the engine's as replies."""
    for uci in line.split():
        state = session.snapshot()
        if state.turn == state.human:
            session.move(state.game_id, len(state.plies), uci)
        else:
            engine.reply(uci)
