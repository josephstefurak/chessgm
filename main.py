#!/usr/bin/env python3
"""Play against the engine in the terminal.

    python main.py                 # asks which colour you want
    python main.py --color b --time 1

Moves can be typed as SAN (Nf3, exd5, O-O) or UCI (g1f3, e4d5, e1g1).
Other commands: undo, help, quit.

This file is only the front end: it reads input, calls the engine, and prints.
"""

from __future__ import annotations

import argparse
import sys

import chess

from engine.search import Limits, Searcher, SearchResult
from opening_book import get_book_move

# --- presentation: change how things look here, not in the logic below ---
FILE_LABELS = "a b c d e f g h"
EMPTY_SQUARE = "."
PROMPT = "Your move: "
DEFAULT_THINK_SECONDS = 2.0
MAX_INPUT_LENGTH = 16  # the longest legal move text is far shorter than this
HELP = "Type a move like Nf3 or g1f3. Commands: undo, help, quit."


def render(board: chess.Board, perspective: chess.Color) -> str:
    """The board as text, drawn from `perspective`'s side of the table."""
    ranks = range(7, -1, -1) if perspective == chess.WHITE else range(8)
    files = range(8) if perspective == chess.WHITE else range(7, -1, -1)
    lines = [""]
    for rank in ranks:
        squares = []
        for file in files:
            piece = board.piece_at(chess.square(file, rank))
            squares.append(piece.symbol() if piece else EMPTY_SQUARE)
        lines.append(f"  {rank + 1}  {' '.join(squares)}")
    labels = FILE_LABELS if perspective == chess.WHITE else FILE_LABELS[::-1]
    lines += ["", f"     {labels}", ""]
    return "\n".join(lines)


def parse_move(board: chess.Board, text: str) -> chess.Move:
    """A legal move from SAN or UCI text. Raises ValueError with a readable message."""
    text = text.strip()
    if not text or len(text) > MAX_INPUT_LENGTH:
        raise ValueError("That is not a move.")
    try:
        return board.parse_san(text)
    except ValueError:
        pass
    try:
        return board.parse_uci(text.lower())
    except ValueError:
        raise ValueError(f"'{text}' is not a legal move here.") from None


def describe_result(board: chess.Board) -> str:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return "Game not finished."
    reason = outcome.termination.name.replace("_", " ").lower()
    if outcome.winner is None:
        return f"Draw ({reason})."
    return f"{'White' if outcome.winner == chess.WHITE else 'Black'} wins by {reason}."


def describe_search(board: chess.Board, result: SearchResult) -> str:
    """Depth, time and evaluation, with the evaluation given from White's side."""
    mate = result.mate_in
    if mate is not None:
        winner = board.turn if mate > 0 else not board.turn
        verdict = f"mate in {abs(mate)} for {'White' if winner == chess.WHITE else 'Black'}"
    else:
        white_score = result.score if board.turn == chess.WHITE else -result.score
        verdict = f"eval {white_score / 100:+.2f}"
    return f"depth {result.depth}, {verdict}, {result.seconds:.1f}s"


def engine_move(board: chess.Board, searcher: Searcher, seconds: float) -> tuple[chess.Move, str]:
    book = get_book_move(board)
    if book is not None:
        return book, "opening book"
    # Stop starting new depths halfway through, so the usual wait is well under `seconds`.
    result = searcher.search(board, Limits(soft_time=seconds * 0.5, hard_time=seconds))
    return result.move, describe_search(board, result)


def ask_colour() -> chess.Color:
    while True:
        answer = input("Play as White or Black? (w/b): ").strip().lower()
        if answer in ("w", "white"):
            return chess.WHITE
        if answer in ("b", "black"):
            return chess.BLACK
        print("Please type w or b.")


def play(human: chess.Color, seconds: float, board: chess.Board) -> None:
    searcher = Searcher()
    print(f"You are {'White' if human == chess.WHITE else 'Black'}. {HELP}")

    while board.outcome(claim_draw=True) is None:
        print(render(board, human))
        if board.turn == human:
            text = input(PROMPT).strip()
            command = text.lower()
            if command in ("quit", "exit"):
                print("Goodbye.")
                return
            if command == "help":
                print(HELP)
                continue
            if command == "undo":
                if len(board.move_stack) >= 2:
                    board.pop()
                    board.pop()
                else:
                    print("Nothing to undo.")
                continue
            try:
                board.push(parse_move(board, text))
            except ValueError as exc:
                print(exc)
        else:
            print("Thinking...")
            move, note = engine_move(board, searcher, seconds)
            print(f"Engine plays {board.san(move)}  ({move.uci()}; {note})")
            board.push(move)

    print(render(board, human))
    print(describe_result(board))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--color", choices=["w", "b"], help="your colour (asked if omitted)")
    parser.add_argument(
        "--time", type=float, default=DEFAULT_THINK_SECONDS, help="most seconds the engine may think per move"
    )
    parser.add_argument("--fen", help="start from this position instead of the initial one")
    args = parser.parse_args(argv)
    if not 0.05 <= args.time <= 600:
        parser.error("--time must be between 0.05 and 600 seconds")

    board = chess.Board()
    if args.fen:
        try:
            board = chess.Board(args.fen)
        except ValueError as exc:
            parser.error(f"bad --fen: {exc}")
        if not board.is_valid():
            parser.error(f"bad --fen: illegal position ({board.status()!r})")

    try:
        human = {"w": chess.WHITE, "b": chess.BLACK}[args.color] if args.color else ask_colour()
        play(human, args.time, board)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
