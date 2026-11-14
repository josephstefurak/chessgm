"""Engine-vs-engine match runner for any two UCI engines.

Used for three things:
  * A/B testing a change (new engine vs the previous version or vs legacy_uci.py)
  * measuring strength against Stockfish at a fixed UCI_Elo
  * checking that an engine respects its time budget (per-move times are reported)

Examples:
    python tools/match.py --a "python uci.py" --b "python legacy_uci.py" --games 40 --movetime 0.5
    python tools/match.py --a "python uci.py" --b /path/to/stockfish \
        --b-opt UCI_LimitStrength=true --b-opt UCI_Elo=1320 --games 40 --movetime 1 --b-movetime 0.1
    python tools/match.py --a "python uci.py" --b "python uci.py" --tc 60+1 --games 8
"""

from __future__ import annotations

import argparse
import logging
import math
import shlex
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
OPENINGS_FILE = Path(__file__).resolve().parent / "openings.txt"
MAX_FULLMOVES = 200

OptionValue = str | int | bool


@dataclass(frozen=True)
class EngineSpec:
    name: str
    cmd: list[str]
    options: dict[str, OptionValue] = field(default_factory=dict)
    movetime: float | None = None  # seconds per move; None means "use the game clock"


@dataclass(frozen=True)
class Clock:
    base: float  # seconds
    inc: float  # seconds added after each move


@dataclass
class SideStats:
    moves: int = 0
    total_time: float = 0.0
    max_time: float = 0.0
    depth_sum: int = 0
    depth_count: int = 0

    def add(self, seconds: float, depth: int | None) -> None:
        self.moves += 1
        self.total_time += seconds
        self.max_time = max(self.max_time, seconds)
        if depth is not None:
            self.depth_sum += depth
            self.depth_count += 1

    def merge(self, other: SideStats) -> None:
        self.moves += other.moves
        self.total_time += other.total_time
        self.max_time = max(self.max_time, other.max_time)
        self.depth_sum += other.depth_sum
        self.depth_count += other.depth_count


@dataclass
class GameResult:
    a_score: float  # 1.0 win, 0.5 draw, 0.0 loss, from engine A's point of view
    a_white: bool
    reason: str
    forfeit: bool  # ended by a crash, an illegal move or the clock rather than by chess
    plies: int
    pgn: str
    a_stats: SideStats
    b_stats: SideStats


@dataclass
class MatchResult:
    wins: int
    draws: int
    losses: int
    a_stats: SideStats
    b_stats: SideStats
    games: list[GameResult]

    @property
    def total(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score(self) -> float:
        return (self.wins + 0.5 * self.draws) / self.total if self.total else 0.0

    @property
    def forfeits(self) -> list[GameResult]:
        return [game for game in self.games if game.forfeit]


def load_openings(path: Path = OPENINGS_FILE) -> list[list[chess.Move]]:
    """Each non-comment line is a space-separated list of UCI moves from the start position.

    Every line is replayed for legality, so a bad file fails loudly instead of skewing a match.
    """
    openings: list[list[chess.Move]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        board = chess.Board()
        moves: list[chess.Move] = []
        for token in line.split():
            try:
                move = board.parse_uci(token)
            except ValueError as exc:
                raise ValueError(f"{path.name}:{lineno}: illegal move {token!r}") from exc
            board.push(move)
            moves.append(move)
        openings.append(moves)
    return openings


def elo_from_score(score: float) -> float | None:
    if score <= 0.0 or score >= 1.0:
        return None
    return -400.0 * math.log10(1.0 / score - 1.0)


def score_interval(wins: int, draws: int, losses: int) -> tuple[float, float]:
    """95% confidence interval on the score, from the per-game variance."""
    n = wins + draws + losses
    if n == 0:
        return 0.0, 1.0
    s = (wins + 0.5 * draws) / n
    var = (wins * (1 - s) ** 2 + draws * (0.5 - s) ** 2 + losses * s**2) / n
    half = 1.96 * math.sqrt(var / n)
    return max(0.0, s - half), min(1.0, s + half)


def _open(spec: EngineSpec) -> chess.engine.SimpleEngine:
    engine = chess.engine.SimpleEngine.popen_uci(spec.cmd, cwd=str(ROOT), timeout=30)
    if spec.options:
        engine.configure(dict(spec.options))
    return engine


def _close(engine: chess.engine.SimpleEngine | None) -> None:
    if engine is None:
        return
    try:
        engine.quit()
    except (chess.engine.EngineError, OSError, TimeoutError):
        engine.close()  # an engine that crashed mid-game cannot be quit politely


def play_game(
    a: EngineSpec,
    b: EngineSpec,
    a_white: bool,
    opening: list[chess.Move],
    clock: Clock | None,
) -> GameResult:
    board = chess.Board()
    for move in opening:
        board.push(move)

    stats = {True: SideStats(), False: SideStats()}  # keyed by "is engine A"
    remaining = {chess.WHITE: clock.base, chess.BLACK: clock.base} if clock else None
    reason = ""
    forfeit = False
    a_score: float | None = None
    game_id = object()
    eng_a: chess.engine.SimpleEngine | None = None
    eng_b: chess.engine.SimpleEngine | None = None

    try:
        # Opened one at a time: if the second fails to start, the first must still be closed
        # in the `finally` below, or its reader thread keeps the whole program alive.
        eng_a = _open(a)
        eng_b = _open(b)
        while a_score is None:
            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                reason = outcome.termination.name.lower()
                if outcome.winner is None:
                    a_score = 0.5
                else:
                    a_score = 1.0 if (outcome.winner == chess.WHITE) == a_white else 0.0
                break
            if board.fullmove_number > MAX_FULLMOVES:
                a_score, reason = 0.5, "move_cap"
                break

            is_a = (board.turn == chess.WHITE) == a_white
            spec, engine = (a, eng_a) if is_a else (b, eng_b)
            if spec.movetime is not None:
                limit = chess.engine.Limit(time=spec.movetime)
            elif clock is not None and remaining is not None:
                limit = chess.engine.Limit(
                    white_clock=remaining[chess.WHITE],
                    black_clock=remaining[chess.BLACK],
                    white_inc=clock.inc,
                    black_inc=clock.inc,
                )
            else:
                raise ValueError(f"{spec.name}: no movetime and no clock")

            started = time.perf_counter()
            try:
                result = engine.play(board, limit, game=game_id, info=chess.engine.INFO_BASIC)
            except chess.engine.EngineError as exc:
                a_score, reason, forfeit = (0.0 if is_a else 1.0), f"{spec.name} error: {exc}", True
                break
            elapsed = time.perf_counter() - started
            stats[is_a].add(elapsed, result.info.get("depth"))

            if spec.movetime is None and clock is not None and remaining is not None:
                remaining[board.turn] -= elapsed
                if remaining[board.turn] < 0:
                    a_score, reason, forfeit = (0.0 if is_a else 1.0), f"{spec.name} lost on time", True
                    break
                remaining[board.turn] += clock.inc

            if result.move is None or result.move not in board.legal_moves:
                a_score, reason, forfeit = (0.0 if is_a else 1.0), f"{spec.name} gave no legal move", True
                break
            board.push(result.move)
    finally:
        _close(eng_a)
        _close(eng_b)

    assert a_score is not None
    game = chess.pgn.Game.from_board(board)
    game.headers["White"] = a.name if a_white else b.name
    game.headers["Black"] = b.name if a_white else a.name
    white_score = a_score if a_white else 1.0 - a_score
    game.headers["Result"] = {1.0: "1-0", 0.5: "1/2-1/2", 0.0: "0-1"}[white_score]
    game.headers["Termination"] = reason
    return GameResult(
        a_score, a_white, reason, forfeit, len(board.move_stack), str(game), stats[True], stats[False]
    )


def run_match(
    a: EngineSpec,
    b: EngineSpec,
    games: int,
    clock: Clock | None = None,
    concurrency: int = 4,
    openings: list[list[chess.Move]] | None = None,
    pgn_path: Path | None = None,
    verbose: bool = True,
) -> MatchResult:
    """Play `games` games. Each opening is played twice with colours swapped, so an
    unbalanced opening cannot favour one engine."""
    if openings is None:
        openings = load_openings()
    if not openings:
        openings = [[]]
    schedule = [(openings[(i // 2) % len(openings)], i % 2 == 0) for i in range(games)]

    result = MatchResult(0, 0, 0, SideStats(), SideStats(), [])
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(play_game, a, b, a_white, opening, clock) for opening, a_white in schedule]
        for number, future in enumerate(futures, 1):
            game = future.result()
            result.games.append(game)
            if game.a_score == 1.0:
                result.wins += 1
            elif game.a_score == 0.5:
                result.draws += 1
            else:
                result.losses += 1
            result.a_stats.merge(game.a_stats)
            result.b_stats.merge(game.b_stats)
            if verbose:
                label = {1.0: "win ", 0.5: "draw", 0.0: "loss"}[game.a_score]
                colour = "W" if game.a_white else "B"
                print(
                    f"game {number:3d}/{games} {a.name}={colour} {label} {game.reason} ({game.plies} plies)"
                    f"   running: +{result.wins} ={result.draws} -{result.losses}",
                    flush=True,
                )
    if pgn_path is not None:
        pgn_path.write_text("\n\n".join(g.pgn for g in result.games) + "\n")
    return result


def format_summary(a: EngineSpec, b: EngineSpec, result: MatchResult) -> str:
    low, high = score_interval(result.wins, result.draws, result.losses)
    headline = (
        f"{a.name} vs {b.name}: +{result.wins} ={result.draws} -{result.losses}"
        f"  score {result.score:.1%} (95% CI {low:.1%} to {high:.1%})"
    )
    lines = [headline]
    forfeits = result.forfeits
    if forfeits:
        # A crashing engine loses every game instantly, which looks like a brilliant result
        # for its opponent. Say so loudly instead of letting it pass as a chess result.
        reasons = sorted({game.reason for game in forfeits})
        lines.append(
            f"WARNING: {len(forfeits)} of {result.total} games were forfeits, not chess results."
            f" This match does not measure strength. Reasons: {'; '.join(reasons)[:300]}"
        )
    elo = elo_from_score(result.score)
    if elo is not None:
        elo_low, elo_high = elo_from_score(low), elo_from_score(high)
        span = (
            f"{elo_low:+.0f} to {elo_high:+.0f}"
            if elo_low is not None and elo_high is not None
            else "interval too wide to state"
        )
        lines.append(f"Elo difference for {a.name}: {elo:+.0f} (95% CI {span})")
    else:
        lines.append("Elo difference: not measurable (one side scored 0% or 100%)")
    for spec, stats in ((a, result.a_stats), (b, result.b_stats)):
        if stats.moves:
            depth = f"{stats.depth_sum / stats.depth_count:.1f}" if stats.depth_count else "n/a"
            lines.append(
                f"  {spec.name}: {stats.total_time / stats.moves:.3f}s avg per move,"
                f" {stats.max_time:.3f}s slowest move, average depth {depth}"
            )
    return "\n".join(lines)


def parse_option(text: str) -> tuple[str, OptionValue]:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"option must look like Name=value, got {text!r}")
    name, raw = text.split("=", 1)
    value: OptionValue
    if raw.lower() in ("true", "false"):
        value = raw.lower() == "true"
    elif raw.lstrip("-").isdigit():
        value = int(raw)
    else:
        value = raw
    return name.strip(), value


def parse_clock(text: str) -> Clock:
    try:
        base, _, inc = text.partition("+")
        clock = Clock(float(base), float(inc) if inc else 0.0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"time control must look like 60+1, got {text!r}") from exc
    if clock.base <= 0 or clock.inc < 0:
        raise argparse.ArgumentTypeError("time control must be positive")
    return clock


def resolve_cmd(text: str) -> list[str]:
    """Split a command line; a leading `python` means the interpreter running this script."""
    parts = shlex.split(text)
    if not parts:
        raise argparse.ArgumentTypeError("empty engine command")
    if parts[0] in ("python", "python3"):
        parts[0] = sys.executable
    return parts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", required=True, type=resolve_cmd, help="command line for engine A")
    parser.add_argument("--b", required=True, type=resolve_cmd, help="command line for engine B")
    parser.add_argument("--a-name", default="A")
    parser.add_argument("--b-name", default="B")
    parser.add_argument("--a-opt", action="append", default=[], type=parse_option, metavar="Name=value")
    parser.add_argument("--b-opt", action="append", default=[], type=parse_option, metavar="Name=value")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--movetime", type=float, help="seconds per move for both engines")
    parser.add_argument("--b-movetime", type=float, help="seconds per move for engine B only")
    parser.add_argument("--tc", type=parse_clock, help="game clock as base+increment in seconds, e.g. 60+1")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--startpos", action="store_true", help="start every game from the initial position")
    parser.add_argument("--pgn", type=Path, help="write all games to this PGN file")
    args = parser.parse_args(argv)

    if args.games < 1:
        parser.error("--games must be at least 1")
    if args.movetime is None and args.tc is None:
        parser.error("give --movetime or --tc")
    if args.movetime is not None and args.movetime <= 0:
        parser.error("--movetime must be positive")

    logging.getLogger("chess.engine").setLevel(logging.ERROR)  # legacy engine prints a non-UCI line
    a = EngineSpec(args.a_name, args.a, dict(args.a_opt), args.movetime)
    b = EngineSpec(args.b_name, args.b, dict(args.b_opt), args.b_movetime or args.movetime)
    openings: list[list[chess.Move]] | None = [[]] if args.startpos else None
    result = run_match(a, b, args.games, args.tc, args.concurrency, openings, args.pgn)
    print()
    print(format_summary(a, b, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
