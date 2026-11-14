"""Chess clocks for the browser GUI.

Pure: the time source is passed in, so tests drive it with a fake clock. The
session decides *when* a clock starts and stops; this module only keeps count.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import chess

ClockState = tuple[float, float]  # seconds left for (White, Black)


@dataclass(frozen=True)
class TimeControl:
    id: str
    initial_seconds: int
    increment_seconds: int


# The controls offered in the new-game dialog. "Untimed" is the absence of a control.
PRESETS: tuple[TimeControl, ...] = (
    TimeControl("3+2", 180, 2),
    TimeControl("5+3", 300, 3),
    TimeControl("10+0", 600, 0),
    TimeControl("15+10", 900, 10),
)


class GameClock:
    def __init__(self, control: TimeControl, now: Callable[[], float]) -> None:
        self.control = control
        self._now = now
        self._left = {
            chess.WHITE: float(control.initial_seconds),
            chess.BLACK: float(control.initial_seconds),
        }
        self._running: chess.Color | None = None
        self._since = 0.0

    @property
    def running(self) -> chess.Color | None:
        return self._running

    def remaining(self, colour: chess.Color) -> float:
        """Seconds left for `colour` right now, never below zero."""
        left = self._left[colour]
        if self._running == colour:
            left -= self._now() - self._since
        return max(left, 0.0)

    def flagged(self) -> chess.Color | None:
        """The side whose running clock has reached zero, if any."""
        if self._running is not None and self.remaining(self._running) <= 0.0:
            return self._running
        return None

    def start(self, colour: chess.Color) -> None:
        self.pause()
        self._running = colour
        self._since = self._now()

    def pause(self) -> None:
        if self._running is not None:
            self._left[self._running] = self.remaining(self._running)
            self._running = None

    def move_made(self, mover: chess.Color) -> None:
        """Stop the clock after `mover` moved. The increment is earned only on a move
        that was timed, so a side's first move (clock not yet started) adds nothing."""
        was_timed = self._running == mover
        self.pause()
        if was_timed:
            self._left[mover] += self.control.increment_seconds

    def state(self) -> ClockState:
        return (self.remaining(chess.WHITE), self.remaining(chess.BLACK))

    def restore(self, state: ClockState) -> None:
        """Set both clocks and leave them stopped. Used by takeback."""
        self._running = None
        self._left = {chess.WHITE: state[0], chess.BLACK: state[1]}

    def initial_state(self) -> ClockState:
        return (float(self.control.initial_seconds), float(self.control.initial_seconds))
