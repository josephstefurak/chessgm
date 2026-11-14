"""Test positions. Every entry was checked against Stockfish (depth 22) when it was
added; the comment gives what Stockfish reported."""

from __future__ import annotations

# Forced mates for the side to move.
MATE_IN_1_WHITE = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"  # Qxf7#
MATE_IN_1_BLACK = "6k1/5ppp/8/8/8/8/r4PPP/6K1 b - - 0 1"  # Ra1#
MATE_IN_2 = "7k/8/8/8/8/8/R7/1R4K1 w - - 0 1"  # Rb7 or Ra7, mate in 2
MATE_IN_3 = "8/8/7k/8/8/8/R7/1R4K1 w - - 0 1"  # Rg2 is the only mate in 3

# Side to move has exactly one legal move and is mated next move.
MATED_IN_1_SINGLE_REPLY = "7k/R7/8/8/8/8/8/1R4K1 b - - 0 1"  # Kg8, then Rb8#

# King and queen vs king: Qf7 and Qg6 stalemate, Kf7 or Qe7 mates in 2.
STALEMATE_TRAP = "7k/8/4QK2/8/8/8/8/8 w - - 0 1"

# Same material with the 50-move counter one ply from a draw.
FIFTY_MOVE_DRAW = "7k/8/4QK2/8/8/8/8/8 w - - 99 80"  # no mate in 1, so it is a draw: 0
FIFTY_MOVE_MATE_FIRST = "7k/8/5K2/8/8/8/8/6Q1 w - - 99 80"  # Qg7# still counts

# White is a rook down but Qd8+ forces perpetual check (0); everything else loses.
PERPETUAL_CHECK = "6k1/5p1p/8/8/8/7P/qr3PPK/3Q4 w - - 0 1"

# White is a queen up; used to build repeated positions by shuffling the kings.
QUEEN_UP = "6k1/5pp1/7p/8/8/8/5PPP/3Q2K1 w - - 0 1"

HANGING_QUEEN = "rnb1kbnr/pppp1ppp/8/4p1q1/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"  # Nxg5
MANY_CAPTURES = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"

# Game already over.
STALEMATED = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
CHECKMATED = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"

# King and pawn vs king, White pawn about to queen, Black to move: White wins.
UNSTOPPABLE_PAWN = "8/P7/8/8/8/8/8/K6k b - - 0 1"
