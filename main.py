import chess
from bot import get_best_move


def print_board(board):
    ranks = str(board).split("\n")
    print()
    for i, rank in enumerate(ranks):
        print(f"  {8 - i}  {rank}")
    print()
    print("     a b c d e f g h")
    print()


def main():
    board = chess.Board()
    print("Chess Bot")
    print("Enter moves in UCI format (e.g. e2e4, g1f3)")
    print("Type 'quit' to exit\n")

    color_input = input("Play as White or Black? (w/b): ").strip().lower()
    human_color = chess.WHITE if color_input == "w" else chess.BLACK
    print("You are", "White" if human_color == chess.WHITE else "Black")
    print()

    while not board.is_game_over():
        print_board(board)

        if board.turn == human_color:
            move_input = input("Your move: ").strip()

            if move_input.lower() == "quit":
                print("Goodbye.")
                break

            try:
                move = chess.Move.from_uci(move_input)
            except ValueError:
                print("Invalid format. Use UCI notation like e2e4.")
                continue

            if move not in board.legal_moves:
                print("Illegal move. Try again.")
                continue

            board.push(move)

        else:
            print("Bot is thinking...")
            move = get_best_move(board, depth=3)
            print(f"Bot plays: {move.uci()}")
            board.push(move)

    print_board(board)
    print("Game over:", board.result())


if __name__ == "__main__":
    main()