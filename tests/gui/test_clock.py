"""The clock model on its own."""

from __future__ import annotations

import chess
import pytest

from tests.gui.fakes import FakeTime
from webgui.server.clock import PRESETS, GameClock, TimeControl

FIVE_THREE = TimeControl("5+3", 300, 3)


def make() -> tuple[GameClock, FakeTime]:
    time = FakeTime()
    return GameClock(FIVE_THREE, time.now), time


def test_starts_full_and_stopped() -> None:
    clock, time = make()
    time.advance(60)
    assert clock.state() == (300.0, 300.0)
    assert clock.running is None
    assert clock.flagged() is None


def test_only_the_running_side_loses_time() -> None:
    clock, time = make()
    clock.start(chess.WHITE)
    time.advance(12.5)
    assert clock.remaining(chess.WHITE) == pytest.approx(287.5)
    assert clock.remaining(chess.BLACK) == 300.0


def test_a_timed_move_earns_the_increment() -> None:
    clock, time = make()
    clock.start(chess.WHITE)
    time.advance(10)
    clock.move_made(chess.WHITE)
    assert clock.remaining(chess.WHITE) == pytest.approx(293.0)
    assert clock.running is None


def test_an_untimed_first_move_earns_nothing() -> None:
    clock, _ = make()
    clock.move_made(chess.WHITE)
    assert clock.remaining(chess.WHITE) == 300.0


def test_flag_falls_at_zero_and_never_goes_negative() -> None:
    clock, time = make()
    clock.start(chess.BLACK)
    time.advance(299.9)
    assert clock.flagged() is None
    time.advance(5)
    assert clock.flagged() == chess.BLACK
    assert clock.remaining(chess.BLACK) == 0.0


def test_restore_sets_both_clocks_and_stops_them() -> None:
    clock, time = make()
    clock.start(chess.WHITE)
    time.advance(50)
    clock.restore((120.0, 45.5))
    time.advance(50)
    assert clock.state() == (120.0, 45.5)
    assert clock.running is None


def test_presets_are_the_ones_documented() -> None:
    assert [control.id for control in PRESETS] == ["3+2", "5+3", "10+0", "15+10"]
    for control in PRESETS:
        minutes, increment = control.id.split("+")
        assert control.initial_seconds == int(minutes) * 60
        assert control.increment_seconds == int(increment)
