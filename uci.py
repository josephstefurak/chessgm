"""
UCI wrapper with time management.
Reads wtime/btime from the go command and allocates time per move dynamically.
"""

import sys
import chess
from bot import get_best_move_timed

# Fraction of remaining time to use per move
# 1/30 means we assume ~30 moves left in the game
TIME_FRACTION = 1 / 30
MIN_MOVE_TIME = 0.1   # never spend less than 0.1s
MAX_MOVE_TIME = 10.0  # never spend more than 10s


def send(msg):
    print(msg, flush=True)


def parse_go(line, board):
    """Parse the go command and return how many seconds to think."""
    parts = line.split()
    wtime = btime = None

    if "movetime" in parts:
        idx = parts.index("movetime")
        return int(parts[idx + 1]) / 1000.0

    if "wtime" in parts:
        idx = parts.index("wtime")
        wtime = int(parts[idx + 1])
    if "btime" in parts:
        idx = parts.index("btime")
        btime = int(parts[idx + 1])

    if board.turn == chess.WHITE and wtime is not None:
        move_time = (wtime / 1000.0) * TIME_FRACTION
    elif board.turn == chess.BLACK and btime is not None:
        move_time = (btime / 1000.0) * TIME_FRACTION
    else:
        move_time = 2.0  # fallback if no time info

    return max(MIN_MOVE_TIME, min(MAX_MOVE_TIME, move_time))


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
            parts = line.split()
            if "startpos" in parts:
                board = chess.Board()
                if "moves" in parts:
                    moves_index = parts.index("moves") + 1
                    for uci in parts[moves_index:]:
                        board.push_uci(uci)
            elif "fen" in parts:
                fen_index = parts.index("fen") + 1
                fen = " ".join(parts[fen_index:fen_index + 6])
                board = chess.Board(fen)
                if "moves" in parts:
                    moves_index = parts.index("moves") + 1
                    for uci in parts[moves_index:]:
                        board.push_uci(uci)

        elif line.startswith("go"):
            move_time = parse_go(line, board)
            move = get_best_move_timed(board, move_time)
            send(f"bestmove {move.uci()}")

        elif line == "quit":
            break


if __name__ == "__main__":
    main()