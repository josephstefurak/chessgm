"""Static evaluation, computed from bitboards.

`evaluate(board)` returns centipawns from White's point of view (positive means
White is better). It never looks at whose turn it is to decide the sign, and it
does not detect checkmate, stalemate or draws: the search does that.

The terms are the same ones the legacy evaluator had (material, piece-square
tables, pawn structure, rooks on open files, king safety, endgame rules), but:
  * every term is White-positive. The legacy evaluator added its positional
    terms, which were White-positive, to a Black-positive total, so they all
    worked backwards.
  * they are computed with bit masks instead of walking squares one at a time.
"""

from __future__ import annotations

import chess
from chess import BB_FILES, BB_KING_ATTACKS, BB_RANKS

from engine import weights as W

WHITE, BLACK = chess.WHITE, chess.BLACK


def _mirror_to_squares(table: list[int], color: chess.Color) -> list[int]:
    """Turn a drawn-from-White's-side table into one indexed by square number for `color`."""
    out = [0] * 64
    for square in range(64):
        rank, file = square >> 3, square & 7
        row = 7 - rank if color == WHITE else rank
        out[square] = table[row * 8 + file]
    return out


def _build_tables(tables: dict[int, list[int]]) -> list[list[list[int]]]:
    """[color][piece_type][square] -> piece value plus square bonus, signed White-positive."""
    built: list[list[list[int]]] = [[[0] * 64 for _ in range(7)] for _ in range(2)]
    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        for piece_type, table in tables.items():
            by_square = _mirror_to_squares(table, color)
            value = W.PIECE_VALUES[piece_type]
            built[color][piece_type] = [sign * (value + bonus) for bonus in by_square]
    return built


_MG = _build_tables(W.TABLES_MG)
_EG = _build_tables(W.TABLES_EG)

# Files next to each file, and for each square the squares a pawn must pass to promote
# (its own file and both neighbours, every rank in front of it).
_ADJACENT_FILES = [
    (BB_FILES[f - 1] if f > 0 else 0) | (BB_FILES[f + 1] if f < 7 else 0) for f in range(8)
]
_PASSED_MASK: list[list[int]] = [[0] * 64, [0] * 64]
for _sq in range(64):
    _f, _r = _sq & 7, _sq >> 3
    _span = BB_FILES[_f] | _ADJACENT_FILES[_f]
    _PASSED_MASK[WHITE][_sq] = _span & sum(BB_RANKS[r] for r in range(_r + 1, 8))
    _PASSED_MASK[BLACK][_sq] = _span & sum(BB_RANKS[r] for r in range(_r))

_pawn_cache: dict[tuple[int, int], int] = {}
_PAWN_CACHE_MAX = 100_000


def clear_caches() -> None:
    _pawn_cache.clear()


def _pawn_structure(white_pawns: int, black_pawns: int) -> int:
    """Passed, doubled and isolated pawns. Depends only on the pawns, so it is cached."""
    key = (white_pawns, black_pawns)
    cached = _pawn_cache.get(key)
    if cached is not None:
        return cached

    score = 0
    bb = white_pawns
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        if not _PASSED_MASK[WHITE][sq] & black_pawns:
            score += W.PASSED_PAWN_BONUS[sq >> 3]
        bb ^= lsb
    bb = black_pawns
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        if not _PASSED_MASK[BLACK][sq] & white_pawns:
            score -= W.PASSED_PAWN_BONUS[7 - (sq >> 3)]
        bb ^= lsb

    for sign, pawns in ((1, white_pawns), (-1, black_pawns)):
        for file in range(8):
            count = (pawns & BB_FILES[file]).bit_count()
            if count:
                if count > 1:
                    score -= sign * W.DOUBLED_PAWN_PENALTY * (count - 1)
                if not pawns & _ADJACENT_FILES[file]:
                    score -= sign * W.ISOLATED_PAWN_PENALTY * count

    if len(_pawn_cache) >= _PAWN_CACHE_MAX:
        _pawn_cache.clear()
    _pawn_cache[key] = score
    return score


def _rooks(board: chess.Board, white_pawns: int, black_pawns: int) -> int:
    score = 0
    for sign, color, own, enemy in ((1, WHITE, white_pawns, black_pawns), (-1, BLACK, black_pawns, white_pawns)):
        bb = board.rooks & board.occupied_co[color]
        while bb:
            lsb = bb & -bb
            file_mask = BB_FILES[(lsb.bit_length() - 1) & 7]
            if not file_mask & own:
                score += sign * (W.ROOK_SEMI_OPEN_FILE_BONUS if file_mask & enemy else W.ROOK_OPEN_FILE_BONUS)
            bb ^= lsb
    return score


def _king_safety(board: chess.Board) -> int:
    """Squares next to each king that the other side attacks."""
    score = 0
    for sign, color in ((1, WHITE), (-1, BLACK)):
        king = board.king(color)
        if king is None:
            continue
        attacked = 0
        bb = BB_KING_ATTACKS[king]
        while bb:
            lsb = bb & -bb
            if board.attackers_mask(not color, lsb.bit_length() - 1):
                attacked += 1
            bb ^= lsb
        score -= sign * attacked * W.KING_ZONE_ATTACK_PENALTY
    return score


def _endgame_rules(board: chess.Board, white_pawns: int, black_pawns: int) -> int:
    score = 0
    white_king, black_king = board.king(WHITE), board.king(BLACK)
    if white_king is None or black_king is None:
        return 0
    minors_and_majors = board.knights | board.bishops | board.rooks | board.queens
    majors = board.rooks | board.queens

    # Rule of the square: a pawn the lone enemy king cannot catch.
    for sign, color, pawns, enemy_king in ((1, WHITE, white_pawns, black_king), (-1, BLACK, black_pawns, white_king)):
        if minors_and_majors & board.occupied_co[not color]:
            continue
        bb = pawns
        while bb:
            lsb = bb & -bb
            sq = lsb.bit_length() - 1
            file, rank = sq & 7, sq >> 3
            to_go = 7 - rank if color == WHITE else rank
            promo_rank = 7 if color == WHITE else 0
            king_dist = max(abs((enemy_king >> 3) - promo_rank), abs((enemy_king & 7) - file))
            if board.turn != color:
                king_dist -= 1
            if king_dist > to_go:
                score += sign * W.UNSTOPPABLE_PAWN_BONUS
            bb ^= lsb

    # Direct opposition belongs to the side that is NOT to move.
    rank_diff = abs((white_king >> 3) - (black_king >> 3))
    file_diff = abs((white_king & 7) - (black_king & 7))
    if (rank_diff == 2 and file_diff == 0) or (rank_diff == 0 and file_diff == 2):
        score += W.OPPOSITION_BONUS if board.turn == BLACK else -W.OPPOSITION_BONUS

    # With a rook or queen against none, drive the enemy king to the edge.
    for sign, color, enemy_king in ((1, WHITE, black_king), (-1, BLACK, white_king)):
        if majors & board.occupied_co[color] and not majors & board.occupied_co[not color]:
            rank, file = enemy_king >> 3, enemy_king & 7
            edge = max(3 - min(rank, 7 - rank), 0) + max(3 - min(file, 7 - file), 0)
            score += sign * edge * W.KING_TO_EDGE_BONUS

    return score


def is_endgame(board: chess.Board) -> bool:
    return _non_pawn_material(board) < W.ENDGAME_THRESHOLD


def _non_pawn_material(board: chess.Board) -> int:
    return (
        board.knights.bit_count() * W.PIECE_VALUES[chess.KNIGHT]
        + board.bishops.bit_count() * W.PIECE_VALUES[chess.BISHOP]
        + board.rooks.bit_count() * W.PIECE_VALUES[chess.ROOK]
        + board.queens.bit_count() * W.PIECE_VALUES[chess.QUEEN]
    )


def material_and_squares(board: chess.Board, endgame: bool) -> int:
    """Piece values plus piece-square bonuses, White-positive."""
    tables = _EG if endgame else _MG
    score = 0
    for color in (WHITE, BLACK):
        own = board.occupied_co[color]
        by_piece = tables[color]
        for piece_type, pieces in (
            (chess.PAWN, board.pawns),
            (chess.KNIGHT, board.knights),
            (chess.BISHOP, board.bishops),
            (chess.ROOK, board.rooks),
            (chess.QUEEN, board.queens),
            (chess.KING, board.kings),
        ):
            bb = pieces & own
            if bb:
                table = by_piece[piece_type]
                while bb:
                    lsb = bb & -bb
                    score += table[lsb.bit_length() - 1]
                    bb ^= lsb
    return score


def evaluate(board: chess.Board) -> int:
    """Centipawns from White's point of view."""
    white_pawns = board.pawns & board.occupied_co[WHITE]
    black_pawns = board.pawns & board.occupied_co[BLACK]
    endgame = is_endgame(board)

    score = material_and_squares(board, endgame)
    score += _pawn_structure(white_pawns, black_pawns)
    score += _rooks(board, white_pawns, black_pawns)
    if endgame:
        score += _endgame_rules(board, white_pawns, black_pawns)
    else:
        score += _king_safety(board)
    return score
