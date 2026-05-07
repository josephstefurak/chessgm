"""
Simple hardcoded opening book.
Covers the most common opening lines for both colors.
Returns a random move from the book for variety, or None if position is unknown.
"""

import chess
import random


def _build_book():
    """
    Build a position -> [moves] dict by playing out known opening lines.
    Each line is a list of UCI moves. Every position along the line gets
    the next move added as a book move.
    """
    book = {}

    lines = [
        # --- White opens e4 ---
        # Ruy Lopez
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"],
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1"],
        # Italian Game
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "c2c3"],
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "d2d3"],
        # Sicilian Defense
        ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3"],
        ["e2e4", "c7c5", "g1f3", "b8c6", "d2d4", "c5d4", "f3d4"],
        ["e2e4", "c7c5", "b1c3", "b8c6", "g2g3", "g7g6", "f1g2"],
        # French Defense
        ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6", "c1g5"],
        ["e2e4", "e7e6", "d2d4", "d7d5", "e4d5", "e6d5", "g1f3"],
        # Caro-Kann
        ["e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4"],
        ["e2e4", "c7c6", "d2d4", "d7d5", "e4e5", "c8f5", "g1f3"],
        # Pirc/Modern
        ["e2e4", "d7d6", "d2d4", "g8f6", "b1c3", "g7g6", "g1f3"],
        # King's Gambit
        ["e2e4", "e7e5", "f2f4", "e5f4", "g1f3", "d7d5", "e4d5"],

        # --- White opens d4 ---
        # Queen's Gambit Declined
        ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c1g5"],
        ["d2d4", "d7d5", "c2c4", "c7c6", "b1c3", "g8f6", "g1f3"],
        # Queen's Gambit Accepted
        ["d2d4", "d7d5", "c2c4", "d5c4", "g1f3", "g8f6", "e2e3"],
        # King's Indian Defense
        ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6", "g1f3"],
        ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "g1f3", "d7d6"],
        # Nimzo-Indian
        ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4", "e2e3"],
        ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4", "d1c2"],
        # Queen's Indian
        ["d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6", "g2g3"],
        # Slav Defense
        ["d2d4", "d7d5", "c2c4", "c7c6", "g1f3", "g8f6", "b1c3", "d5c4"],
        # London System
        ["d2d4", "d7d5", "g1f3", "g8f6", "c1f4", "e7e6", "e2e3"],
        ["d2d4", "g8f6", "g1f3", "e7e6", "c1f4", "d7d5", "e2e3"],

        # --- White opens Nf3 ---
        ["g1f3", "d7d5", "d2d4", "g8f6", "c2c4", "e7e6"],
        ["g1f3", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "d2d4"],

        # --- White opens c4 (English) ---
        ["c2c4", "e7e5", "b1c3", "g8f6", "g1f3", "b8c6", "g2g3"],
        ["c2c4", "g8f6", "b1c3", "d7d5", "c4d5", "f6d5", "g2g3"],
    ]

    for line in lines:
        board = chess.Board()
        for uci in line:
            key = board._transposition_key()
            move = chess.Move.from_uci(uci)
            if key not in book:
                book[key] = []
            if move not in book[key]:
                book[key].append(move)
            board.push(move)

    return book


_BOOK = _build_book()


def get_book_move(board):
    """
    Returns a random book move for the current position, or None if not in book.
    Randomness adds opening variety so the bot doesn't always play identically.
    """
    key = board._transposition_key()
    moves = _BOOK.get(key)
    if not moves:
        return None
    # Filter to only legal moves (sanity check)
    legal = [m for m in moves if m in board.legal_moves]
    if not legal:
        return None
    return random.choice(legal)
