#!/usr/bin/env python3
"""UCI front end. This is the program lichess-bot (or any chess GUI) launches.

It only translates: UCI text in, engine calls, UCI text out. All chess logic
lives in the `engine` package. Nothing but UCI is ever written to stdout.

The search runs on its own thread so that `stop`, `isready` and `quit` are
answered while the engine is thinking, and so that a closed stdin ends the
process instead of leaving it spinning.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from dataclasses import fields, replace

import chess

from engine import evaluation, timeman
from engine.search import Limits, SearchConfig, Searcher, SearchInfo
from opening_book import get_book_move

ENGINE_NAME = "chessgm"
ENGINE_AUTHOR = "josephstefurak"

MAX_LINE_LENGTH = 65_536  # a 600-move game is under 4 KB; anything bigger is not UCI
MAX_CLOCK_MS = 24 * 60 * 60 * 1000
FALLBACK_MOVETIME_MS = 1000  # used when a `go` command cannot be parsed
TT_ENTRIES_PER_MB = 2_500  # rough: one table entry plus its eval-cache entry is about 400 bytes

# UCI option name -> SearchConfig field. These exist so each technique can be A/B tested.
SEARCH_TOGGLES: dict[str, str] = {
    "NullMove": "null_move",
    "LMR": "late_move_reductions",
    "ReverseFutility": "reverse_futility",
    "Futility": "futility",
    "Aspiration": "aspiration",
    "CheckExtension": "check_extension",
    "BadCapturePruning": "bad_capture_pruning",
}
assert set(SEARCH_TOGGLES.values()) == {f.name for f in fields(SearchConfig)}

GO_INT_PARAMS = ("wtime", "btime", "winc", "binc", "movestogo", "movetime", "depth", "nodes")


class UciEngine:
    def __init__(self, write: Callable[[str], None]) -> None:
        self._write_line = write
        self._write_lock = threading.Lock()
        self.board = chess.Board()
        self.move_overhead_ms = 30
        self.hash_mb = 128
        self.own_book = True
        self.config = SearchConfig()
        self.searcher = Searcher(self.config, self.hash_mb * TT_ENTRIES_PER_MB)
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- output

    def send(self, text: str) -> None:
        with self._write_lock:
            self._write_line(text)

    def _info(self, info: SearchInfo) -> None:
        mate = info.mate_in
        score = f"mate {mate}" if mate is not None else f"cp {info.score}"
        ms = int(info.seconds * 1000)
        nps = int(info.nodes / info.seconds) if info.seconds > 0 else 0
        pv = " ".join(move.uci() for move in info.pv)
        self.send(f"info depth {info.depth} score {score} nodes {info.nodes} nps {nps} time {ms} pv {pv}")

    # --------------------------------------------------------------- commands

    def handle(self, line: str) -> bool:
        """Process one line of input. Returns False when the engine should exit."""
        if len(line) > MAX_LINE_LENGTH:
            self.send("info string ignored: input line too long")
            return True
        tokens = line.split()
        if not tokens:
            return True
        command, args = tokens[0], tokens[1:]

        if command == "uci":
            self._identify()
        elif command == "isready":
            self.send("readyok")
        elif command == "ucinewgame":
            self.stop_search()
            self.searcher.new_game()
            evaluation.clear_caches()
            self.board = chess.Board()
        elif command == "setoption":
            self.stop_search()
            self._set_option(args)
        elif command == "position":
            self.stop_search()
            self._set_position(args)
        elif command == "go":
            self.stop_search()
            self._go(args)
        elif command == "stop":
            self.stop_search()
        elif command == "quit":
            self.stop_search()
            return False
        # Anything else is ignored, as the UCI protocol requires.
        return True

    def _identify(self) -> None:
        self.send(f"id name {ENGINE_NAME}")
        self.send(f"id author {ENGINE_AUTHOR}")
        self.send(f"option name Move Overhead type spin default {self.move_overhead_ms} min 0 max 5000")
        self.send(f"option name Hash type spin default {self.hash_mb} min 1 max 2048")
        self.send("option name OwnBook type check default true")
        for name in SEARCH_TOGGLES:
            self.send(f"option name {name} type check default true")
        self.send("uciok")

    def _set_option(self, args: list[str]) -> None:
        # setoption name <name, may contain spaces> [value <value>]
        if not args or args[0] != "name":
            self.send("info string ignored: malformed setoption")
            return
        if "value" in args:
            split = args.index("value")
            name, value = " ".join(args[1:split]), " ".join(args[split + 1 :])
        else:
            name, value = " ".join(args[1:]), ""
        key = name.lower()

        try:
            if key == "move overhead":
                self.move_overhead_ms = _bounded_int(value, 0, 5000)
            elif key == "hash":
                self.hash_mb = _bounded_int(value, 1, 2048)
                self.searcher = Searcher(self.config, self.hash_mb * TT_ENTRIES_PER_MB)
            elif key == "ownbook":
                self.own_book = _parse_bool(value)
            else:
                toggle = next((field for opt, field in SEARCH_TOGGLES.items() if opt.lower() == key), None)
                if toggle is None:
                    self.send(f"info string ignored: unknown option {name!r}")
                    return
                self.config = replace(self.config, **{toggle: _parse_bool(value)})
                self.searcher.config = self.config
        except ValueError as exc:
            self.send(f"info string ignored: bad value for {name!r}: {exc}")

    def _set_position(self, args: list[str]) -> None:
        # position [startpos | fen <fen>] [moves <move> ...]
        # Built on a scratch board so a bad command leaves the current position untouched.
        try:
            if "moves" in args:
                split = args.index("moves")
                setup, moves = args[:split], args[split + 1 :]
            else:
                setup, moves = args, []
            if setup == ["startpos"]:
                board = chess.Board()
            elif setup and setup[0] == "fen":
                board = chess.Board(" ".join(setup[1:]))
                if not board.is_valid():
                    raise ValueError(f"illegal position ({board.status()!r})")
            else:
                raise ValueError("expected 'startpos' or 'fen'")
            for text in moves:
                board.push_uci(text)  # raises ValueError on a malformed or illegal move
        except ValueError as exc:
            self.send(f"info string ignored: bad position command: {exc}")
            return
        self.board = board

    def _go(self, args: list[str]) -> None:
        params: dict[str, int] = {}
        try:
            for name in GO_INT_PARAMS:
                if name in args:
                    index = args.index(name) + 1
                    if index >= len(args):
                        raise ValueError(f"{name} needs a value")
                    params[name] = _bounded_int(args[index], 0, MAX_CLOCK_MS)
        except ValueError as exc:
            # Still answer with a move: a GUI that sent a broken `go` is waiting for one.
            self.send(f"info string bad go command, thinking for {FALLBACK_MOVETIME_MS} ms instead: {exc}")
            params = {"movetime": FALLBACK_MOVETIME_MS}
        infinite = "infinite" in args and "movetime" not in params

        board = self.board.copy()
        if not any(board.legal_moves):
            self.send("bestmove 0000")  # mate or stalemate on the board: there is no move to give
            return

        limits, uses_clock = self._limits(board, params, infinite)
        if uses_clock and self.own_book:
            book_move = get_book_move(board)
            if book_move is not None:
                self.send(f"bestmove {book_move.uci()}")
                return

        self._thread = threading.Thread(target=self._search, args=(board, limits), daemon=True)
        self._thread.start()

    def _limits(self, board: chess.Board, params: dict[str, int], infinite: bool) -> tuple[Limits, bool]:
        """Returns the search limits and whether this is a normal timed move (book allowed)."""
        overhead = self.move_overhead_ms / 1000.0
        depth = params.get("depth") or None
        nodes = params.get("nodes") or None
        if infinite:
            return Limits(depth=depth, nodes=nodes), False
        if "movetime" in params:
            budget = timeman.fixed(params["movetime"] / 1000.0, overhead)
            return Limits(budget.soft, budget.hard, depth, nodes), True
        clock_key, inc_key = ("wtime", "winc") if board.turn == chess.WHITE else ("btime", "binc")
        if clock_key in params:
            budget = timeman.allocate(
                params[clock_key] / 1000.0,
                params.get(inc_key, 0) / 1000.0,
                params.get("movestogo") or None,
                overhead,
            )
            return Limits(budget.soft, budget.hard, depth, nodes), True
        # No time information: search until told to stop (or to the given depth/nodes).
        return Limits(depth=depth, nodes=nodes), False

    def _search(self, board: chess.Board, limits: Limits) -> None:
        try:
            result = self.searcher.search(board, limits, self._info)
            self.send(f"bestmove {result.move.uci()}")
        except Exception as exc:  # noqa: BLE001 - never leave the GUI waiting for a bestmove
            self.send(f"info string search error: {type(exc).__name__}: {exc}")
            fallback = next(iter(board.legal_moves), None)
            self.send(f"bestmove {fallback.uci() if fallback else '0000'}")

    def stop_search(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            self.searcher.stop()
            thread.join()
        self._thread = None


def _bounded_int(text: str, low: int, high: int) -> int:
    value = int(text)  # raises ValueError on anything that is not an integer
    if not low <= value <= high:
        raise ValueError(f"{value} is outside {low}..{high}")
    return value


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(f"expected true or false, got {text!r}")


def main() -> int:
    def write(text: str) -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    engine = UciEngine(write)
    try:
        for line in sys.stdin:  # ends when stdin is closed, so an orphaned engine exits
            if not engine.handle(line):
                break
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        engine.stop_search()
    return 0


if __name__ == "__main__":
    sys.exit(main())
