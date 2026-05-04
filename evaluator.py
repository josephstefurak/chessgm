import chess
import os
import pickle
from features import extract_features

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "model.pkl")
_model = None
if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        _model = pickle.load(f)
    print("Loaded trained model.")

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Total material threshold below which we switch to endgame king table
# 1500 = roughly both sides down to rook + a few pawns
ENDGAME_THRESHOLD = 1500

PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]

QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]

# Middlegame king table — stay safe, castle, hide
KING_TABLE_MG = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]

# Endgame king table — centralize, support pawns, be active
KING_TABLE_EG = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]

TABLES_MG = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
    chess.KING: KING_TABLE_MG,
}

TABLES_EG = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
    chess.KING: KING_TABLE_EG,
}


def is_endgame(board):
    """Returns True when total non-pawn, non-king material drops below threshold."""
    total = 0
    for piece_type in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        for color in [chess.WHITE, chess.BLACK]:
            total += len(board.pieces(piece_type, color)) * PIECE_VALUES[piece_type]
    return total < ENDGAME_THRESHOLD


def piece_square_bonus(piece_type, square, color, endgame):
    tables = TABLES_EG if endgame else TABLES_MG
    table = tables.get(piece_type, [0] * 64)
    rank = chess.square_rank(square)
    file = chess.square_file(square)
    if color == chess.WHITE:
        index = (7 - rank) * 8 + file
    else:
        index = rank * 8 + file
    return table[index]


def passed_pawn_bonus(board):
    score = 0
    advancement_bonus = [0, 10, 20, 40, 70, 110, 160, 0]

    for square in board.pieces(chess.PAWN, chess.WHITE):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        is_passed = True
        for r in range(rank + 1, 8):
            for f in range(max(0, file - 1), min(7, file + 1) + 1):
                sq = chess.square(f, r)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == chess.BLACK:
                    is_passed = False
                    break
        if is_passed:
            score += advancement_bonus[rank]

    for square in board.pieces(chess.PAWN, chess.BLACK):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        is_passed = True
        for r in range(0, rank):
            for f in range(max(0, file - 1), min(7, file + 1) + 1):
                sq = chess.square(f, r)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == chess.WHITE:
                    is_passed = False
                    break
        if is_passed:
            score -= advancement_bonus[7 - rank]

    return score


def pawn_structure_penalty(board):
    score = 0
    DOUBLED_PENALTY = 20
    ISOLATED_PENALTY = 15

    for color in [chess.WHITE, chess.BLACK]:
        sign = 1 if color == chess.WHITE else -1
        pawns = board.pieces(chess.PAWN, color)
        files = [chess.square_file(sq) for sq in pawns]

        for f in range(8):
            count = files.count(f)
            if count > 1:
                score -= sign * DOUBLED_PENALTY * (count - 1)

        for f in files:
            has_neighbor = (f - 1) in files or (f + 1) in files
            if not has_neighbor:
                score -= sign * ISOLATED_PENALTY

    return score


def rook_open_file_bonus(board):
    score = 0
    OPEN_BONUS = 25
    SEMI_OPEN_BONUS = 10

    for color in [chess.WHITE, chess.BLACK]:
        sign = 1 if color == chess.WHITE else -1
        for square in board.pieces(chess.ROOK, color):
            file = chess.square_file(square)
            file_squares = [chess.square(file, r) for r in range(8)]

            friendly_pawn = any(
                board.piece_at(sq) and board.piece_at(sq).piece_type == chess.PAWN
                and board.piece_at(sq).color == color
                for sq in file_squares
            )
            enemy_pawn = any(
                board.piece_at(sq) and board.piece_at(sq).piece_type == chess.PAWN
                and board.piece_at(sq).color != color
                for sq in file_squares
            )

            if not friendly_pawn and not enemy_pawn:
                score += sign * OPEN_BONUS
            elif not friendly_pawn:
                score += sign * SEMI_OPEN_BONUS

    return score


def king_safety_penalty(board):
    score = 0
    ATTACKER_PENALTY = 10

    for color in [chess.WHITE, chess.BLACK]:
        sign = 1 if color == chess.WHITE else -1
        enemy = not color
        king_sq = board.king(color)
        if king_sq is None:
            continue

        king_rank = chess.square_rank(king_sq)
        king_file = chess.square_file(king_sq)

        attackers = 0
        for dr in [-1, 0, 1]:
            for df in [-1, 0, 1]:
                if dr == 0 and df == 0:
                    continue
                r = king_rank + dr
                f = king_file + df
                if 0 <= r <= 7 and 0 <= f <= 7:
                    sq = chess.square(f, r)
                    if board.is_attacked_by(enemy, sq):
                        attackers += 1

        score -= sign * attackers * ATTACKER_PENALTY

    return score


def evaluate(board):
    if board.is_checkmate():
        if board.turn == chess.BLACK:
            return -10000
        else:
            return 10000

    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    endgame = is_endgame(board)
    score = 0

    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece is None:
            continue
        value = PIECE_VALUES[piece.piece_type]
        value += piece_square_bonus(piece.piece_type, square, piece.color, endgame)
        if piece.color == chess.BLACK:
            score += value
        else:
            score -= value

    score += passed_pawn_bonus(board)
    score += pawn_structure_penalty(board)
    score += rook_open_file_bonus(board)

    # Only apply king safety penalty in middlegame — in endgame the king should be active
    if not endgame:
        score += king_safety_penalty(board)

    if _model is not None:
        features = extract_features(board)
        ml_score = _model.predict([features])[0]
        return score + int(ml_score * 100)

    return score