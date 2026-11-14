#!/usr/bin/env python3
"""Play the engine against Stockfish at a fixed rating and estimate its strength.

    python match.py --elo 1320 --games 40
    python match.py --elo 1700 --games 40 --movetime 1

The engine plays through uci.py with its real timed search, exactly as it does
on Lichess. This is a shortcut for tools/match.py, which can pit any two UCI
engines against each other.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from tools.match import EngineSpec, format_summary, run_match

DEFAULT_STOCKFISH = "/Users/josephstefurak/stockfish/stockfish-macos-m1-apple-silicon"
STOCKFISH_MIN_ELO = 1320  # Stockfish refuses anything lower
STOCKFISH_MAX_ELO = 3190
ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--elo", type=int, default=STOCKFISH_MIN_ELO, help="Stockfish UCI_Elo")
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--movetime", type=float, default=1.0, help="seconds per move for our engine")
    parser.add_argument("--sf-movetime", type=float, default=0.1, help="seconds per move for Stockfish")
    parser.add_argument("--concurrency", type=int, default=6, help="games played at the same time")
    parser.add_argument(
        "--stockfish",
        default=os.environ.get("CHESSGM_STOCKFISH", DEFAULT_STOCKFISH),
        help="path to the Stockfish binary (or set CHESSGM_STOCKFISH)",
    )
    parser.add_argument("--pgn", type=Path, help="write the games to this PGN file")
    args = parser.parse_args(argv)

    if not STOCKFISH_MIN_ELO <= args.elo <= STOCKFISH_MAX_ELO:
        parser.error(f"--elo must be between {STOCKFISH_MIN_ELO} and {STOCKFISH_MAX_ELO}")
    if args.games < 1 or args.concurrency < 1:
        parser.error("--games and --concurrency must be at least 1")
    if args.movetime <= 0 or args.sf_movetime <= 0:
        parser.error("move times must be positive")
    if not Path(args.stockfish).is_file():
        parser.error(f"Stockfish not found at {args.stockfish}")

    ours = EngineSpec("chessgm", [sys.executable, str(ROOT / "uci.py")], {}, args.movetime)
    stockfish = EngineSpec(
        f"stockfish-{args.elo}",
        [args.stockfish],
        {"UCI_LimitStrength": True, "UCI_Elo": args.elo},
        args.sf_movetime,
    )
    print(f"{args.games} games, chessgm at {args.movetime}s/move vs Stockfish at {args.elo} Elo\n")
    result = run_match(ours, stockfish, args.games, concurrency=args.concurrency, pgn_path=args.pgn)
    print()
    print(format_summary(ours, stockfish, result))
    low_note = "Stockfish's limited-strength ratings are approximate; treat the Elo figure as a guide."
    print(low_note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
