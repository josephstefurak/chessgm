"""Speed benchmark for the engine on a fixed set of positions.

Two modes:
    python tools/bench.py                 # 1 second per position: depth reached and nodes/s
    python tools/bench.py --depth 6       # fixed depth: node count (deterministic) and time

Fixed depth is the one to use when checking that a refactor did not change
behaviour: the node counts must be identical before and after.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import evaluation
from engine.search import Limits, Searcher, SearchResult

POSITIONS: list[tuple[str, str]] = [
    ("opening, Italian", "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R b KQkq - 0 4"),
    ("opening, Queen's Gambit", "rnbqkb1r/ppp2ppp/4pn2/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 2 4"),
    ("middlegame, open centre", "r2q1rk1/pp2bppp/2n1bn2/3p4/3P4/2NBBN2/PP3PPP/R2Q1RK1 w - - 0 11"),
    ("middlegame, many captures", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("middlegame, closed", "r1bq1rk1/pp2ppbp/2np1np1/8/2PNP3/2N1B3/PP2BPPP/R2Q1RK1 b - - 4 9"),
    ("middlegame, attack", "r1b2rk1/2q1bppp/p2p1n2/np2p3/3PP3/2P2N1P/PPBN1PP1/R1BQR1K1 b - - 0 13"),
    ("rook endgame", "8/5pk1/6p1/8/1R6/6P1/r4PK1/8 w - - 0 40"),
    ("pawn endgame", "8/2k5/3p4/p2P1p2/P2P1P2/8/3K4/8 w - - 0 1"),
    ("queen endgame", "8/5pk1/6p1/8/8/3Q2P1/q4PK1/8 w - - 0 40"),
    ("minor piece endgame", "8/pp3pk1/2n3p1/8/8/6P1/PP1B1PK1/8 w - - 0 30"),
]


def run(depth: int | None, seconds: float) -> list[SearchResult]:
    results = []
    total_nodes = 0
    total_time = 0.0
    print(f"{'position':28s} {'depth':>5s} {'nodes':>9s} {'time':>7s} {'nodes/s':>8s}  move   score")
    for name, fen in POSITIONS:
        searcher = Searcher()
        evaluation.clear_caches()
        board = chess.Board(fen)
        limits = Limits(depth=depth) if depth is not None else Limits(soft_time=seconds, hard_time=seconds)
        result = searcher.search(board, limits)
        results.append(result)
        total_nodes += result.nodes
        total_time += result.seconds
        mate = result.mate_in
        score = f"mate {mate}" if mate is not None else f"{result.score:+d}"
        print(
            f"{name:28s} {result.depth:5d} {result.nodes:9d} {result.seconds:6.2f}s"
            f" {result.nodes / max(result.seconds, 1e-9):8.0f}  {result.move.uci():6s} {score}"
        )
    average_depth = sum(r.depth for r in results) / len(results)
    print(
        f"{'TOTAL':28s} {average_depth:5.1f} {total_nodes:9d} {total_time:6.2f}s"
        f" {total_nodes / max(total_time, 1e-9):8.0f}"
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, help="search every position to this fixed depth")
    parser.add_argument("--seconds", type=float, default=1.0, help="time per position when no depth is given")
    args = parser.parse_args(argv)
    if args.depth is not None and args.depth < 1:
        parser.error("--depth must be at least 1")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    run(args.depth, args.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
