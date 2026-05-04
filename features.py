import chess


def extract_features(board):
    """
    Converts a board state into a flat feature vector for ML training.
    Returns a list of floats from White's perspective.
    Positive values favor White, negative favor Black.
    """
    features = []

    # 1. Material balance per piece type (White - Black count)
    for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        white_count = len(board.pieces(piece_type, chess.WHITE))
        black_count = len(board.pieces(piece_type, chess.BLACK))
        features.append(white_count - black_count)

    # 2. Mobility (number of legal moves available to each side)
    # Approximate: count moves for current side, then flip and count for other
    if board.turn == chess.WHITE:
        white_mobility = len(list(board.legal_moves))
        board.push(chess.Move.null())
        black_mobility = len(list(board.legal_moves))
        board.pop()
    else:
        black_mobility = len(list(board.legal_moves))
        board.push(chess.Move.null())
        white_mobility = len(list(board.legal_moves))
        board.pop()

    features.append(white_mobility - black_mobility)

    # 3. Center control (pieces/pawns attacking center squares)
    CENTER = [chess.E4, chess.D4, chess.E5, chess.D5]
    white_center = sum(
        1 for sq in CENTER if board.is_attacked_by(chess.WHITE, sq)
    )
    black_center = sum(
        1 for sq in CENTER if board.is_attacked_by(chess.BLACK, sq)
    )
    features.append(white_center - black_center)

    # 4. King safety (proximity to center is dangerous - use rank/file distance from edge)
    white_king_sq = board.king(chess.WHITE)
    black_king_sq = board.king(chess.BLACK)

    def king_safety_score(sq):
        rank = chess.square_rank(sq)
        file = chess.square_file(sq)
        # Distance from center = safer (higher is better)
        return min(rank, 7 - rank) + min(file, 7 - file)

    features.append(king_safety_score(white_king_sq) - king_safety_score(black_king_sq))

    # 5. Is in check
    features.append(1 if board.is_check() and board.turn == chess.BLACK else 0)
    features.append(1 if board.is_check() and board.turn == chess.WHITE else 0)

    return features


FEATURE_NAMES = [
    "pawn_diff",
    "knight_diff",
    "bishop_diff",
    "rook_diff",
    "queen_diff",
    "mobility_diff",
    "center_control_diff",
    "king_safety_diff",
    "black_in_check",
    "white_in_check",
]
