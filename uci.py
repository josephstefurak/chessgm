"""
UCI (Universal Chess Interface) wrapper.
Allows the bot to be used with any UCI-compatible chess GUI or bridge (like lichess-bot).

Run with: python uci.py
"""

import sys
import chess
from bot import get_best_move

SEARCH_DEPTH = 3


def send(msg):
    print(msg, flush=True)


def main():
    board = chess.Board()

    while True:
        line = sys.stdin.readline().strip()
        if not line:
            continue

        if line == "uci":
            send("id name ChessBot")
            send("id author You")
            send("uciok")

        elif line == "isready":
            send("readyok")

        elif line == "ucinewgame":
            board = chess.Board()

        elif line.startswith("position"):
            # Format: position startpos moves e2e4 e7e5 ...
            # or:     position fen <fen> moves ...
            parts = line.split()
            if "startpos" in parts:
                board = chess.Board()
                if "moves" in parts:
                    moves_index = parts.index("moves") + 1
                    for uci in parts[moves_index:]:
                        board.push_uci(uci)
            elif "fen" in parts:
                fen_index = parts.index("fen") + 1
                # FEN is 6 space-separated tokens
                fen = " ".join(parts[fen_index:fen_index + 6])
                board = chess.Board(fen)
                if "moves" in parts:
                    moves_index = parts.index("moves") + 1
                    for uci in parts[moves_index:]:
                        board.push_uci(uci)

        elif line.startswith("go"):
            move = get_best_move(board, depth=SEARCH_DEPTH)
            send(f"bestmove {move.uci()}")

        elif line == "quit":
            break


if __name__ == "__main__":
    main()
