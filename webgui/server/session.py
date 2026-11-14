"""The one game the GUI is playing. All of its state and every rule live here.

The browser sends intents (`move`, `takeback`, `resign`, `new_game`) and is sent
back a `Snapshot`. Nothing here knows about HTTP.

Threading: requests arrive on server threads, engine callbacks on the engine's
worker thread and the flag timer on its own thread. One re-entrant lock guards
all state. `_generation` changes whenever the position the engine was asked about
stops being the position on the board, so a late answer is recognised and dropped.

Score convention: the engine reports scores from the side to move. They are
converted to White's point of view in `_score_out` and nowhere else.
"""

from __future__ import annotations

import datetime as dt
import random
import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

import chess
import chess.pgn

from engine import timeman
from engine.search import Limits, SearchInfo
from webgui.server import schemas as wire
from webgui.server.clock import PRESETS, ClockState, GameClock, TimeControl
from webgui.server.engine_port import EngineMove, EnginePort

ENGINE_NAME = "chessgm"
HUMAN_NAME = "Human"
FLAG_TIMER_SLACK = 0.02  # seconds past zero before the timer looks, so it never looks early

Cancel = Callable[[], None]
Schedule = Callable[[float, Callable[[], None]], Cancel]


class SessionError(Exception):
    """A request the game cannot carry out. `code` is a stable machine-readable name."""

    status = 400

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Conflict(SessionError):
    """The request was valid but no longer fits the game (stale, wrong turn, game over)."""

    status = 409


class Rejected(SessionError):
    """The request asks for something that is not allowed (an illegal move)."""

    status = 422


@dataclass(frozen=True)
class _Ply:
    san: str
    uci: str
    fen: str
    check: bool
    capture: bool
    clock: ClockState | None


@dataclass
class _EngineStatus:
    state: Literal["idle", "thinking", "error"] = "idle"
    source: Literal["book", "search"] | None = None
    ply: int | None = None
    depth: int | None = None
    score: wire.ScoreOut | None = None
    pv_san: list[str] = field(default_factory=list)
    nodes: int | None = None
    ms: int | None = None
    error: str | None = None


def _thread_timer(delay: float, callback: Callable[[], None]) -> Cancel:
    timer = threading.Timer(delay, callback)
    timer.daemon = True
    timer.start()
    return timer.cancel


def _colour_name(colour: chess.Color) -> wire.Colour:
    return "white" if colour == chess.WHITE else "black"


def _score_out(info: SearchInfo, side_to_move: chess.Color) -> wire.ScoreOut:
    """The engine's side-to-move score, turned to White's point of view."""
    sign = 1 if side_to_move == chess.WHITE else -1
    mate = info.mate_in
    if mate is not None:
        return wire.ScoreOut(mate=sign * mate)
    return wire.ScoreOut(cp=sign * info.score)


def _line_san(board: chess.Board, line: Sequence[chess.Move]) -> list[str]:
    """SAN for a line of moves from `board`, stopping at the first move that does not fit."""
    replay = board.copy(stack=False)
    names: list[str] = []
    for move in line:
        if move not in replay.legal_moves:
            break
        names.append(replay.san(move))
        replay.push(move)
    return names


class GameSession:
    def __init__(
        self,
        engine: EnginePort,
        *,
        think_seconds: float,
        time_controls: Sequence[TimeControl] = PRESETS,
        now: Callable[[], float] = time.monotonic,
        schedule: Schedule | None = _thread_timer,
        today: Callable[[], dt.date] = dt.date.today,
        rng: random.Random | None = None,
    ) -> None:
        """`think_seconds` is the most the engine may think per move in an untimed game.
        `schedule` runs the flag check when a clock is due to run out; pass None to
        drive `tick()` by hand."""
        self._engine = engine
        self._think_seconds = think_seconds
        self._controls = {control.id: control for control in time_controls}
        self._now = now
        self._schedule = schedule
        self._today = today
        self._rng = rng or random.Random()

        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self._cancel_flag_timer: Cancel | None = None
        self._version = 0
        self._generation = 0
        self._closed = False

        # Set properly by _reset; declared here so the attributes always exist.
        self._game_id = ""
        self._date = self._today()
        self._human: chess.Color = chess.WHITE
        self._board = chess.Board()
        self._plies: list[_Ply] = []
        self._result: wire.ResultOut | None = None
        self._clock: GameClock | None = None
        self._status = _EngineStatus()

        with self._lock:
            self._reset(chess.WHITE, None)

    # --------------------------------------------------------------- listeners

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """`listener` is called after every change, possibly on another thread and
        with the session lock held, so it must return at once. Returns the unsubscribe."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    # ----------------------------------------------------------------- intents

    def new_game(self, human: wire.ColourChoice, time_control: str | None) -> wire.Snapshot:
        with self._lock:
            control: TimeControl | None = None
            if time_control is not None:
                control = self._controls.get(time_control)
                if control is None:
                    raise Rejected("unknown_time_control")
            if human == "random":
                colour = self._rng.choice([chess.WHITE, chess.BLACK])
            else:
                colour = chess.WHITE if human == "white" else chess.BLACK
            self._reset(colour, control)
            return self._snapshot()

    def move(self, game_id: str, ply: int, uci: str) -> wire.Snapshot:
        with self._lock:
            self._require_current(game_id, ply)
            self._require_playing()
            if self._board.turn != self._human:
                raise Conflict("not_your_turn")
            try:
                move = self._board.parse_uci(uci)
            except ValueError:
                raise Rejected("illegal_move") from None
            self._push(move)
            if self._result is None:
                self._ask_engine()
            return self._snapshot()

    def takeback(self, game_id: str, ply: int) -> wire.Snapshot:
        with self._lock:
            self._require_current(game_id, ply)
            self._require_playing()
            count = self._takeback_plies()
            if count == 0:
                raise Conflict("nothing_to_take_back")
            self._engine.cancel()
            self._generation += 1
            for _ in range(count):
                self._board.pop()
                self._plies.pop()
            if self._clock is not None:
                earlier = self._plies[-1].clock if self._plies else None
                self._clock.restore(earlier or self._clock.initial_state())
                self._start_clock()
            self._status = _EngineStatus()
            self._changed()
            return self._snapshot()

    def resign(self, game_id: str) -> wire.Snapshot:
        with self._lock:
            if game_id != self._game_id:
                raise Conflict("stale_game")
            self._require_playing()
            self._finish(not self._human, "resignation")
            self._changed()
            return self._snapshot()

    def tick(self) -> None:
        """Look at the clocks. Safe to call at any time; the flag timer calls it."""
        with self._lock:
            if self._closed:
                return
            self._check_flag()
            self._arm_flag_timer()

    def snapshot(self) -> wire.Snapshot:
        with self._lock:
            self._check_flag()
            return self._snapshot()

    def pgn(self) -> str:
        with self._lock:
            return self._pgn()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._generation += 1
            self._disarm_flag_timer()
            self._listeners.clear()
        self._engine.close()

    # --------------------------------------------------------- engine callbacks

    def _on_info(self, generation: int, info: SearchInfo) -> None:
        with self._lock:
            if generation != self._generation or self._result is not None:
                return
            self._status = self._status_from(info, "thinking")
            self._changed()

    def _on_done(self, generation: int, answer: EngineMove) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._check_flag()
            if self._result is not None:
                return
            if answer.move not in self._board.legal_moves:
                self._engine_failed("IllegalMove")
                return
            if answer.info is not None:
                self._status = self._status_from(answer.info, "idle")
            else:
                self._status = _EngineStatus(source=answer.source, ply=len(self._plies))
            self._push(answer.move)

    def _on_error(self, generation: int, error: Exception) -> None:
        with self._lock:
            if generation != self._generation or self._result is not None:
                return
            self._engine_failed(type(error).__name__)

    def _engine_failed(self, name: str) -> None:
        # The game stays where it is: the human can take back or start again.
        self._status = _EngineStatus(state="error", error=name)
        self._changed()

    def _status_from(self, info: SearchInfo, state: Literal["idle", "thinking"]) -> _EngineStatus:
        return _EngineStatus(
            state=state,
            source="search",
            ply=len(self._plies),
            depth=info.depth,
            score=_score_out(info, self._board.turn),
            pv_san=_line_san(self._board, info.pv),
            nodes=info.nodes,
            ms=int(info.seconds * 1000),
        )

    # ------------------------------------------------------- internals (locked)

    def _reset(self, human: chess.Color, control: TimeControl | None) -> None:
        self._engine.new_game()  # also cancels whatever it was doing
        self._generation += 1
        self._game_id = secrets.token_hex(8)
        self._date = self._today()
        self._human = human
        self._board = chess.Board()
        self._plies = []
        self._result = None
        self._clock = GameClock(control, self._now) if control is not None else None
        self._status = _EngineStatus()
        self._changed()
        if self._board.turn != self._human:
            self._ask_engine()

    def _require_current(self, game_id: str, ply: int) -> None:
        if game_id != self._game_id:
            raise Conflict("stale_game")
        if ply != len(self._plies):
            raise Conflict("stale_position")

    def _require_playing(self) -> None:
        self._check_flag()
        if self._result is not None:
            raise Conflict("game_over")

    def _takeback_plies(self) -> int:
        """How many plies a takeback removes: the human's move alone while the engine
        is still thinking about it, otherwise the engine's reply and the move before it."""
        if self._result is not None:
            return 0
        if self._board.turn != self._human:
            return 1 if self._plies else 0
        return 2 if len(self._plies) >= 2 else 0

    def _push(self, move: chess.Move) -> None:
        mover = self._board.turn
        san = self._board.san(move)
        capture = self._board.is_capture(move)
        self._board.push(move)
        if self._clock is not None:
            self._clock.move_made(mover)
        self._plies.append(
            _Ply(
                san=san,
                uci=move.uci(),
                fen=self._board.fen(),
                check=self._board.is_check(),
                capture=capture,
                clock=self._clock.state() if self._clock is not None else None,
            )
        )
        ending = self._ending()
        if ending is not None:
            self._finish(*ending)
        else:
            self._start_clock()
        self._changed()

    def _ending(self) -> tuple[chess.Color | None, wire.Reason] | None:
        """Why the game on the board is over, if it is.

        Draws by repetition and the 50-move rule are automatic, but only once they
        have actually happened. `outcome(claim_draw=True)`, which main.py uses, also
        ends the game when the side to move merely *could* repeat with its next move;
        in a GUI that calls a draw one move before the board shows it, and takes the
        choice to play on away from a player who is winning.
        """
        outcome = self._board.outcome(claim_draw=False)
        if outcome is not None:
            return outcome.winner, cast(wire.Reason, outcome.termination.name.lower())
        if self._board.is_fifty_moves():
            return None, "fifty_moves"
        if self._board.is_repetition(3):
            return None, "threefold_repetition"
        return None

    def _start_clock(self) -> None:
        # Each side's clock first runs on its second move, so nobody loses time
        # looking at a fresh board.
        if self._clock is not None and len(self._plies) >= 2:
            self._clock.start(self._board.turn)

    def _finish(self, winner: chess.Color | None, reason: wire.Reason) -> None:
        self._engine.cancel()
        self._generation += 1
        if self._clock is not None:
            self._clock.pause()
        self._result = wire.ResultOut(winner=None if winner is None else _colour_name(winner), reason=reason)
        if self._status.state != "idle":
            self._status = _EngineStatus()

    def _check_flag(self) -> None:
        if self._result is not None or self._clock is None:
            return
        flagged = self._clock.flagged()
        if flagged is None:
            return
        opponent = not flagged
        if self._board.has_insufficient_material(opponent):
            self._finish(None, "timeout_insufficient_material")
        else:
            self._finish(opponent, "timeout")
        self._changed()

    def _ask_engine(self) -> None:
        self._generation += 1
        generation = self._generation
        # Keep the last score so the eval bar does not jump to the middle while thinking.
        self._status = _EngineStatus(state="thinking", score=self._status.score)
        self._changed()
        self._engine.request_move(
            self._board.copy(),
            self._engine_limits(),
            lambda info: self._on_info(generation, info),
            lambda answer: self._on_done(generation, answer),
            lambda error: self._on_error(generation, error),
        )

    def _engine_limits(self) -> Limits:
        if self._clock is None:
            # The same policy as main.py: stop starting new depths halfway through.
            return Limits(soft_time=self._think_seconds * 0.5, hard_time=self._think_seconds)
        budget = timeman.allocate(
            self._clock.remaining(self._board.turn), float(self._clock.control.increment_seconds)
        )
        return Limits(soft_time=budget.soft, hard_time=budget.hard)

    def _changed(self) -> None:
        self._version += 1
        self._arm_flag_timer()
        for listener in list(self._listeners):
            listener()

    def _disarm_flag_timer(self) -> None:
        if self._cancel_flag_timer is not None:
            self._cancel_flag_timer()
            self._cancel_flag_timer = None

    def _arm_flag_timer(self) -> None:
        self._disarm_flag_timer()
        if self._schedule is None or self._closed or self._result is not None or self._clock is None:
            return
        running = self._clock.running
        if running is not None:
            delay = self._clock.remaining(running) + FLAG_TIMER_SLACK
            self._cancel_flag_timer = self._schedule(delay, self.tick)

    # ------------------------------------------------------------------ output

    def _snapshot(self) -> wire.Snapshot:
        playing = self._result is None
        dests: dict[str, list[str]] = {}
        promotions: list[str] = []
        if playing and self._board.turn == self._human:
            for move in self._board.legal_moves:
                origin, target = chess.square_name(move.from_square), chess.square_name(move.to_square)
                targets = dests.setdefault(origin, [])
                if target not in targets:
                    targets.append(target)
                if move.promotion and origin + target not in promotions:
                    promotions.append(origin + target)

        plies: list[wire.PlyOut] = []
        for index, ply in enumerate(self._plies):
            # After White's move (odd ply number) it is Black who may be in check.
            checked: wire.Colour = "black" if index % 2 == 0 else "white"
            plies.append(
                wire.PlyOut(
                    ply=index + 1,
                    san=ply.san,
                    uci=ply.uci,
                    fen=ply.fen,
                    check=checked if ply.check else None,
                    capture=ply.capture,
                    clock=_clock_pair(ply.clock) if ply.clock is not None else None,
                )
            )

        clock: wire.ClockOut | None = None
        if self._clock is not None:
            pair = _clock_pair(self._clock.state())
            running = self._clock.running
            clock = wire.ClockOut(
                white_ms=pair.white_ms,
                black_ms=pair.black_ms,
                running=None if running is None else _colour_name(running),
            )

        status = self._status
        return wire.Snapshot(
            game_id=self._game_id,
            version=self._version,
            human=_colour_name(self._human),
            status="playing" if playing else "finished",
            result=self._result,
            turn=_colour_name(self._board.turn),
            start_fen=chess.STARTING_FEN,
            plies=plies,
            legal=wire.LegalOut(dests=dests, promotions=promotions),
            actions=wire.ActionsOut(takeback=self._takeback_plies() > 0, resign=playing),
            time_control=self._clock.control.id if self._clock is not None else None,
            time_controls=[
                wire.TimeControlOut(
                    id=control.id,
                    initial_ms=control.initial_seconds * 1000,
                    increment_ms=control.increment_seconds * 1000,
                )
                for control in self._controls.values()
            ],
            clock=clock,
            engine=wire.EngineOut(
                state=status.state,
                source=status.source,
                ply=status.ply,
                depth=status.depth,
                score=status.score,
                pv_san=list(status.pv_san),
                nodes=status.nodes,
                ms=status.ms,
                error=status.error,
            ),
            pgn=self._pgn(),
        )

    def _pgn(self) -> str:
        game = chess.pgn.Game.from_board(self._board)
        human_is_white = self._human == chess.WHITE
        game.headers["Event"] = "Casual game"
        game.headers["Site"] = "Local"
        game.headers["Date"] = self._date.strftime("%Y.%m.%d")
        game.headers["Round"] = "-"
        game.headers["White"] = HUMAN_NAME if human_is_white else ENGINE_NAME
        game.headers["Black"] = ENGINE_NAME if human_is_white else HUMAN_NAME
        game.headers["Result"] = self._result_code()
        if self._clock is not None:
            control = self._clock.control
            game.headers["TimeControl"] = f"{control.initial_seconds}+{control.increment_seconds}"
        else:
            game.headers["TimeControl"] = "-"
        if self._result is not None and self._result.reason.startswith("timeout"):
            game.headers["Termination"] = "time forfeit"
        return str(game) + "\n"

    def _result_code(self) -> str:
        if self._result is None:
            return "*"
        if self._result.winner is None:
            return "1/2-1/2"
        return "1-0" if self._result.winner == "white" else "0-1"


def _clock_pair(state: ClockState) -> wire.ClockPair:
    return wire.ClockPair(white_ms=int(state[0] * 1000), black_ms=int(state[1] * 1000))
