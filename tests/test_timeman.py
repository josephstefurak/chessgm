from __future__ import annotations

import pytest

from engine import timeman


@pytest.mark.parametrize("remaining", [0.5, 5, 60, 600, 3600])
@pytest.mark.parametrize("increment", [0, 1, 10])
def test_budget_is_sane(remaining: float, increment: float) -> None:
    budget = timeman.allocate(remaining, increment)
    assert 0 < budget.soft <= budget.hard
    assert budget.hard <= remaining * 0.5  # one move can never cost more than half the clock


def test_more_clock_means_more_time() -> None:
    assert timeman.allocate(600).soft > timeman.allocate(60).soft


def test_increment_is_used() -> None:
    assert timeman.allocate(60, 5).soft > timeman.allocate(60, 0).soft


def test_moves_to_go_is_used() -> None:
    assert timeman.allocate(60, moves_to_go=5).soft > timeman.allocate(60).soft


def test_almost_no_time_left_gives_the_minimum() -> None:
    budget = timeman.allocate(0.02, overhead=0.03)
    assert budget.soft == budget.hard == timeman.MINIMUM


def test_ten_minute_game_opening_move_is_a_reasonable_wait() -> None:
    budget = timeman.allocate(600)
    assert 4 < budget.soft < 12


def test_whole_game_never_runs_out_of_clock() -> None:
    """Spending the hard limit on every single move, with no increment, for 100 moves
    must still leave time on the clock."""
    remaining = 300.0
    for _ in range(100):
        remaining -= timeman.allocate(remaining).hard
        assert remaining > 0


def test_fixed_move_time() -> None:
    budget = timeman.fixed(1.0, overhead=0.03)
    assert budget.soft == budget.hard == pytest.approx(0.97)
    assert timeman.fixed(0.01, overhead=0.03).hard == pytest.approx(0.005)
