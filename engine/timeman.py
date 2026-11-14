"""Turn the clock situation into a time budget for one move.

The search gets two numbers:
  * soft: once this much time has passed, do not start another depth. A new depth
    usually costs several times the previous one, so starting it late is wasted work.
  * hard: stop no matter what.
"""

from __future__ import annotations

from dataclasses import dataclass

# With no moves-to-go information, plan as if this many of our moves remain.
ASSUMED_MOVES_LEFT = 40
# Share of the increment added to each move's budget.
INCREMENT_SHARE = 0.8
# Never plan to spend more than this share of the remaining clock on one move.
MAX_SHARE_OF_CLOCK = 0.35
# Never let the hard limit exceed this share of the remaining clock.
HARD_SHARE_OF_CLOCK = 0.5
SOFT_FRACTION = 0.55  # soft limit as a fraction of the planned time
HARD_MULTIPLE = 2.5  # hard limit as a multiple of the planned time
MINIMUM = 0.005


@dataclass(frozen=True)
class TimeBudget:
    soft: float
    hard: float


def allocate(
    remaining: float,
    increment: float = 0.0,
    moves_to_go: int | None = None,
    overhead: float = 0.03,
) -> TimeBudget:
    """All arguments and results are in seconds.

    `overhead` is time lost between the engine deciding and the move arriving
    (process pipes, network); it is taken off the clock before planning.
    """
    usable = max(remaining - overhead, 0.0)
    if usable <= MINIMUM:
        return TimeBudget(MINIMUM, MINIMUM)

    moves = ASSUMED_MOVES_LEFT
    if moves_to_go is not None and moves_to_go > 0:
        moves = min(moves_to_go + 1, ASSUMED_MOVES_LEFT)

    planned = usable / moves + INCREMENT_SHARE * max(increment, 0.0)
    planned = min(planned, usable * MAX_SHARE_OF_CLOCK)
    soft = max(planned * SOFT_FRACTION, MINIMUM)
    hard = max(min(planned * HARD_MULTIPLE, usable * HARD_SHARE_OF_CLOCK), soft)
    return TimeBudget(soft, hard)


def fixed(move_time: float, overhead: float = 0.03) -> TimeBudget:
    """Budget for `go movetime`: use the whole time, minus the overhead."""
    usable = max(move_time - min(overhead, move_time * 0.5), MINIMUM)
    return TimeBudget(usable, usable)
