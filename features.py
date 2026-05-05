import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def extract_features(board):
    features = []

    # 1. Material balance per piece type (White - Black count)
    for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        white_count = len(board.pieces(piece_type, chess.WHITE))
        black_count = len(board.pieces(piece_type, chess.BLACK))
        features.append(white_count - black_count)

    # 2. Mobility (total legal moves available to each side)
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

    # 3. Center control
    CENTER = [chess.E4, chess.D4, chess.E5, chess.D5]
    white_center = sum(1 for sq in CENTER if board.is_attacked_by(chess.WHITE, sq))
    black_center = sum(1 for sq in CENTER if board.is_attacked_by(chess.BLACK, sq))
    features.append(white_center - black_center)

    # 4. King safety (distance from center)
    white_king_sq = board.king(chess.WHITE)
    black_king_sq = board.king(chess.BLACK)

    def king_safety_score(sq):
        rank = chess.square_rank(sq)
        file = chess.square_file(sq)
        return min(rank, 7 - rank) + min(file, 7 - file)

    features.append(king_safety_score(white_king_sq) - king_safety_score(black_king_sq))

    # 5. Is in check
    features.append(1 if board.is_check() and board.turn == chess.BLACK else 0)
    features.append(1 if board.is_check() and board.turn == chess.WHITE else 0)

    # 6. Bishop pair bonus
    white_bishop_pair = 1 if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2 else 0
    black_bishop_pair = 1 if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2 else 0
    features.append(white_bishop_pair - black_bishop_pair)

    # 7. Knight mobility (squares each side's knights can move to)
    def knight_mobility(color):
        total = 0
        for sq in board.pieces(chess.KNIGHT, color):
            total += len(list(board.attacks(sq)))
        return total

    features.append(knight_mobility(chess.WHITE) - knight_mobility(chess.BLACK))

    # 8. Bishop mobility (squares each side's bishops can move to)
    def bishop_mobility(color):
        total = 0
        for sq in board.pieces(chess.BISHOP, color):
            total += len(list(board.attacks(sq)))
        return total

    features.append(bishop_mobility(chess.WHITE) - bishop_mobility(chess.BLACK))

    # 9. Pawn advancement (average rank of pawns, weighted by count)
    def pawn_advancement(color):
        pawns = board.pieces(chess.PAWN, color)
        if not pawns:
            return 0
        if color == chess.WHITE:
            return sum(chess.square_rank(sq) for sq in pawns) / len(pawns)
        else:
            # For Black, advancement is measured from rank 7 downward
            return sum(7 - chess.square_rank(sq) for sq in pawns) / len(pawns)

    features.append(pawn_advancement(chess.WHITE) - pawn_advancement(chess.BLACK))

    # 10. Rook on 7th rank (2nd rank for Black)
    white_rook_7th = sum(
        1 for sq in board.pieces(chess.ROOK, chess.WHITE)
        if chess.square_rank(sq) == 6  # rank 7 (0-indexed)
    )
    black_rook_7th = sum(
        1 for sq in board.pieces(chess.ROOK, chess.BLACK)
        if chess.square_rank(sq) == 1  # rank 2 (0-indexed)
    )
    features.append(white_rook_7th - black_rook_7th)

    # 11. Open king file (no pawns in front of king)
    def open_king_file(color):
        king_sq = board.king(color)
        if king_sq is None:
            return 0
        file = chess.square_file(king_sq)
        for rank in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.PAWN and piece.color == color:
                return 0
        return 1

    features.append(open_king_file(chess.WHITE) - open_king_file(chess.BLACK))

    # 12. King-pawn distance in endgame (how close king is to its own passed pawns)
    def king_pawn_distance(color):
        king_sq = board.king(color)
        if king_sq is None:
            return 0
        pawns = board.pieces(chess.PAWN, color)
        if not pawns:
            return 0
        king_rank = chess.square_rank(king_sq)
        king_file = chess.square_file(king_sq)
        total_dist = 0
        for sq in pawns:
            pawn_rank = chess.square_rank(sq)
            pawn_file = chess.square_file(sq)
            dist = max(abs(king_rank - pawn_rank), abs(king_file - pawn_file))
            total_dist += dist
        return total_dist / len(pawns)

    # Negative because closer is better (smaller distance = stronger position)
    features.append(-(king_pawn_distance(chess.WHITE) - king_pawn_distance(chess.BLACK)))

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
    "bishop_pair_diff",
    "knight_mobility_diff",
    "bishop_mobility_diff",
    "pawn_advancement_diff",
    "rook_on_7th_diff",
    "open_king_file_diff",
    "king_pawn_distance_diff",
]