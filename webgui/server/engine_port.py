"""The GUI's view of the engine: ask for a move, get told when it arrives.

`SearchEngine` is the real one. It owns the `Searcher` on a single long-lived
worker thread and runs one job at a time, because the evaluation caches are
module-global and two searches must never overlap.

Cancelling needs care. `Searcher.search` clears its stop flag when it starts, so a
`stop()` that lands just before a search begins is lost and that search would run
to its full time limit. Every job therefore carries a number: the worker skips a
job that is already out of date, and checks again each time a depth completes
(depth 1 takes a few milliseconds), stopping the search itself if it has gone stale.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

import chess

from engine import evaluation
from engine.search import Limits, Searcher, SearchInfo
from opening_book import get_book_move


@dataclass(frozen=True)
class EngineMove:
    move: chess.Move
    source: Literal["book", "search"]
    info: SearchInfo | None  # None for a book move: there was no search to report


OnInfo = Callable[[SearchInfo], None]
OnDone = Callable[[EngineMove], None]
OnError = Callable[[Exception], None]


class EnginePort(Protocol):
    """Callbacks may arrive on any thread, including before `request_move` returns.
    A request replaces any earlier one; a cancelled request never calls back."""

    def request_move(
        self, board: chess.Board, limits: Limits, on_info: OnInfo, on_done: OnDone, on_error: OnError
    ) -> None: ...

    def cancel(self) -> None: ...

    def new_game(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class _SearchJob:
    number: int
    board: chess.Board
    limits: Limits
    on_info: OnInfo
    on_done: OnDone
    on_error: OnError


class _ResetJob:
    """Clear everything the engine remembers from the previous game."""


class SearchEngine:
    def __init__(self, searcher: Searcher | None = None) -> None:
        self._searcher = searcher or Searcher()
        self._jobs: queue.SimpleQueue[_SearchJob | _ResetJob | None] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._current = 0  # number of the only job still wanted
        self._thread = threading.Thread(target=self._run, name="chessgm-engine", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ any thread

    def request_move(
        self, board: chess.Board, limits: Limits, on_info: OnInfo, on_done: OnDone, on_error: OnError
    ) -> None:
        number = self._supersede()
        self._jobs.put(_SearchJob(number, board, limits, on_info, on_done, on_error))

    def cancel(self) -> None:
        self._supersede()

    def new_game(self) -> None:
        self._supersede()
        self._jobs.put(_ResetJob())

    def close(self) -> None:
        self._supersede()
        self._jobs.put(None)
        self._thread.join(timeout=2.0)

    def _supersede(self) -> int:
        with self._lock:
            self._current += 1
            number = self._current
        self._searcher.stop()
        return number

    def _stale(self, number: int) -> bool:
        with self._lock:
            return number != self._current

    # ---------------------------------------------------------- worker thread

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            if isinstance(job, _ResetJob):
                self._searcher.new_game()
                evaluation.clear_caches()
            elif not self._stale(job.number):
                self._play(job)

    def _play(self, job: _SearchJob) -> None:
        def on_info(info: SearchInfo) -> None:
            if self._stale(job.number):
                self._searcher.stop()  # repeats a stop that the search may have erased on entry
            else:
                job.on_info(info)

        try:
            book_move = get_book_move(job.board)
            if book_move is not None:
                answer = EngineMove(book_move, "book", None)
            else:
                result = self._searcher.search(job.board, job.limits, on_info)
                info = SearchInfo(result.depth, result.score, result.nodes, result.seconds, result.pv)
                answer = EngineMove(result.move, "search", info)
        except Exception as exc:  # noqa: BLE001 - the game must hear about it rather than hang
            if not self._stale(job.number):
                job.on_error(exc)
            return
        if not self._stale(job.number):
            job.on_done(answer)
