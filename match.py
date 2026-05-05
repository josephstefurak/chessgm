"""
Play your bot against Stockfish at a specified ELO and report results.

Requirements:
    pip install chess
    Download Stockfish from https://stockfishchess.org/download/
    Set STOCKFISH_PATH below to wherever you put the binary.

Usage:
    python match.py --elo 1000 --games 20
    python match.py --elo 1200 --games 10
"""

import argparse
import chess
import chess.engine
from bot import get_best_move

STOCKFISH_PATH = "/Users/josephstefurak/stockfish/stockfish-macos-m1-apple-silicon"
BOT_DEPTH = 3


def play_game(stockfish_elo, bot_color):
    """
    Play one game. bot_color is chess.WHITE or chess.BLACK.
    Returns 1 if bot wins, 0 if draw, -1 if bot loses.
    """
    board = chess.Board()
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    engine.configure({"UCI_LimitStrength": True, "UCI_Elo": stockfish_elo})

    try:
        while not board.is_game_over():
            if board.turn == bot_color:
                move = get_best_move(board, depth=BOT_DEPTH)
            else:
                result = engine.play(board, chess.engine.Limit(time=0.1))
                move = result.move
            board.push(move)
    finally:
        engine.quit()

    outcome = board.outcome()
    if outcome is None or outcome.winner is None:
        return 0  # draw
    if outcome.winner == bot_color:
        return 1  # bot wins
    return -1  # bot loses


def run_match(stockfish_elo, num_games):
    wins = draws = losses = 0

    for i in range(num_games):
        # Alternate colors each game
        bot_color = chess.WHITE if i % 2 == 0 else chess.BLACK
        color_str = "White" if bot_color == chess.WHITE else "Black"

        print(f"Game {i + 1}/{num_games} (Bot plays {color_str})...", end=" ", flush=True)
        result = play_game(stockfish_elo, bot_color)

        if result == 1:
            wins += 1
            print("Bot wins")
        elif result == 0:
            draws += 1
            print("Draw")
        else:
            losses += 1
            print("Bot loses")

    total = wins + draws + losses
    score = (wins + 0.5 * draws) / total
    print(f"\n--- Results vs Stockfish {stockfish_elo} ELO ---")
    print(f"Wins: {wins}  Draws: {draws}  Losses: {losses}")
    print(f"Score: {score:.1%}")

    # Rough ELO estimate based on score
    # ELO diff = -400 * log10(1/score - 1)
    if 0 < score < 1:
        import math
        elo_diff = -400 * math.log10(1 / score - 1)
        estimated_elo = stockfish_elo + elo_diff
        print(f"Estimated bot ELO: ~{estimated_elo:.0f}")
    elif score == 1.0:
        print("Bot won every game — try a higher Stockfish ELO")
    else:
        print("Bot lost every game — try a lower Stockfish ELO")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--elo", type=int, default=1000, help="Stockfish ELO to play against")
    parser.add_argument("--games", type=int, default=20, help="Number of games to play")
    args = parser.parse_args()

    print(f"Playing {args.games} games against Stockfish at {args.elo} ELO...")
    print(f"Bot depth: {BOT_DEPTH}\n")
    run_match(args.elo, args.games)
