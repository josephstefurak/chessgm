"""Static evaluation, computed from bitboards.

`evaluate(board)` returns centipawns from White's point of view (positive means
White is better). It does not detect checkmate, stalemate or draws: the search
does that.

How it works
------------
Most terms have a middlegame value and an endgame value. Both are accumulated
at once and blended at the end by how much material is left ("tapered" eval),
so there is no sudden jump when the game crosses into an endgame.

To keep the inner loops short, a (middlegame, endgame) pair is packed into one
integer: `(eg << 16) + mg`. Packed values can be added and negated like normal
numbers and are split apart once, at the end.

Every term is White-positive. The legacy evaluator added White-positive
positional terms to a Black-positive total, so they all worked backwards; the
colour-symmetry test in tests/test_evaluation.py exists to stop that recurring.
"""

from __future__ import annotations

import chess
from chess import BB_FILES, BB_RANKS

from engine import weights as W

WHITE, BLACK = chess.WHITE, chess.BLACK


def _pack(mg: int, eg: int) -> int:
    return (eg << 16) + mg


def _unpack(packed: int) -> tuple[int, int]:
    mg = ((packed + 0x8000) & 0xFFFF) - 0x8000
    return mg, (packed - mg) >> 16


def _blend(mg: int, eg: int, phase: int) -> int:
    """Mix by game phase. Rounds toward zero so that swapping colours exactly negates."""
    value = mg * phase + eg * (W.PHASE_MAX - phase)
    return value // W.PHASE_MAX if value >= 0 else -(-value // W.PHASE_MAX)


def _build_piece_tables() -> list[list[list[int]]]:
    """[color][piece_type][square] -> packed (piece value + square bonus), White-positive."""
    built: list[list[list[int]]] = [[[0] * 64 for _ in range(7)] for _ in range(2)]
    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        for piece_type in chess.PIECE_TYPES:
            table = built[color][piece_type]
            for square in range(64):
                rank, file = square >> 3, square & 7
                # Tables are drawn from White's side with rank 8 first; Black reads them mirrored.
                index = (7 - rank if color == WHITE else rank) * 8 + file
                mg = W.PIECE_VALUES_MG[piece_type] + W.TABLES_MG[piece_type][index]
                eg = W.PIECE_VALUES_EG[piece_type] + W.TABLES_EG[piece_type][index]
                table[square] = sign * _pack(mg, eg)
    return built


_PIECE = _build_piece_tables()

# Files next to each file; and for each square, the squares in front of a pawn there.
_ADJACENT_FILES = [(BB_FILES[f - 1] if f > 0 else 0) | (BB_FILES[f + 1] if f < 7 else 0) for f in range(8)]
_AHEAD: list[list[int]] = [[0] * 64, [0] * 64]  # every rank in front, all files
_PASSED_MASK: list[list[int]] = [[0] * 64, [0] * 64]  # own file and neighbours, in front
_PATH: list[list[int]] = [[0] * 64, [0] * 64]  # own file only, in front
for _sq in range(64):
    _f, _r = _sq & 7, _sq >> 3
    _AHEAD[WHITE][_sq] = sum(BB_RANKS[r] for r in range(_r + 1, 8))
    _AHEAD[BLACK][_sq] = sum(BB_RANKS[r] for r in range(_r))
    for _c in (WHITE, BLACK):
        _PASSED_MASK[_c][_sq] = (BB_FILES[_f] | _ADJACENT_FILES[_f]) & _AHEAD[_c][_sq]
        _PATH[_c][_sq] = BB_FILES[_f] & _AHEAD[_c][_sq]

# King shelter: the three files around the king, and the two ranks of squares in front of it.
_KING_FILES = [BB_FILES[sq & 7] | _ADJACENT_FILES[sq & 7] for sq in range(64)]
_SHIELD_NEAR: list[list[int]] = [[0] * 64, [0] * 64]
_SHIELD_FAR: list[list[int]] = [[0] * 64, [0] * 64]
for _sq in range(64):
    _r = _sq >> 3
    if _r <= 1:  # White king on rank 1 or 2
        _SHIELD_NEAR[WHITE][_sq] = _KING_FILES[_sq] & BB_RANKS[_r + 1]
        _SHIELD_FAR[WHITE][_sq] = _KING_FILES[_sq] & BB_RANKS[_r + 2]
    if _r >= 6:  # Black king on rank 8 or 7
        _SHIELD_NEAR[BLACK][_sq] = _KING_FILES[_sq] & BB_RANKS[_r - 1]
        _SHIELD_FAR[BLACK][_sq] = _KING_FILES[_sq] & BB_RANKS[_r - 2]

_PASSED = [_pack(mg, eg) for mg, eg in zip(W.PASSED_PAWN_MG, W.PASSED_PAWN_EG, strict=True)]
_DOUBLED = _pack(W.DOUBLED_PAWN_MG, W.DOUBLED_PAWN_EG)
_ISOLATED = _pack(W.ISOLATED_PAWN_MG, W.ISOLATED_PAWN_EG)
_ROOK_OPEN = _pack(W.ROOK_OPEN_FILE_MG, W.ROOK_OPEN_FILE_EG)
_ROOK_SEMI_OPEN = _pack(W.ROOK_SEMI_OPEN_FILE_MG, W.ROOK_SEMI_OPEN_FILE_EG)
_BISHOP_PAIR = _pack(W.BISHOP_PAIR_MG, W.BISHOP_PAIR_EG)

_pawn_cache: dict[tuple[int, int], int] = {}
_shelter_cache: dict[tuple[int, int], int] = {}
_PAWN_CACHE_MAX = 100_000


def clear_caches() -> None:
    _pawn_cache.clear()
    _shelter_cache.clear()


def _pawn_structure(white_pawns: int, black_pawns: int) -> int:
    """Passed, doubled and isolated pawns (packed). Depends only on the pawns, so it is cached."""
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
            score += _PASSED[sq >> 3]
        bb ^= lsb
    bb = black_pawns
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        if not _PASSED_MASK[BLACK][sq] & white_pawns:
            score -= _PASSED[7 - (sq >> 3)]
        bb ^= lsb

    for sign, pawns in ((1, white_pawns), (-1, black_pawns)):
        for file in range(8):
            count = (pawns & BB_FILES[file]).bit_count()
            if count:
                if count > 1:
                    score -= sign * _DOUBLED * (count - 1)
                if not pawns & _ADJACENT_FILES[file]:
                    score -= sign * _ISOLATED * count

    if len(_pawn_cache) >= _PAWN_CACHE_MAX:
        _pawn_cache.clear()
    _pawn_cache[key] = score
    return score


def _rooks(white_rooks: int, black_rooks: int, white_pawns: int, black_pawns: int) -> int:
    """Rooks on open and half-open files (packed)."""
    score = 0
    for sign, bb, own, enemy in ((1, white_rooks, white_pawns, black_pawns), (-1, black_rooks, black_pawns, white_pawns)):
        while bb:
            lsb = bb & -bb
            file_mask = BB_FILES[(lsb.bit_length() - 1) & 7]
            if not file_mask & own:
                score += sign * (_ROOK_SEMI_OPEN if file_mask & enemy else _ROOK_OPEN)
            bb ^= lsb
    return score


def _king_shelter(king: int, color: chess.Color, own_pawns: int) -> int:
    """Middlegame-only value of the pawns in front of a king that is still on its home ranks.

    Kings and pawns move rarely compared with how often positions are evaluated, so the
    answer is cached. (The two colours cannot collide: a king square on ranks 1-2 is
    always White's shelter and one on ranks 7-8 always Black's.)
    """
    near = _SHIELD_NEAR[color][king]
    if not near:
        return 0  # the king has left its first two ranks: the king table already punishes that
    key = (king, own_pawns)
    cached = _shelter_cache.get(key)
    if cached is not None:
        return cached
    value = (own_pawns & near).bit_count() * W.PAWN_SHIELD_NEAR
    value += (own_pawns & _SHIELD_FAR[color][king]).bit_count() * W.PAWN_SHIELD_FAR
    file = king & 7
    for f in range(max(0, file - 1), min(7, file + 1) + 1):
        if not own_pawns & BB_FILES[f]:
            value -= W.KING_OPEN_FILE_PENALTY
    if len(_shelter_cache) >= _PAWN_CACHE_MAX:
        _shelter_cache.clear()
    _shelter_cache[key] = value
    return value


def _unstoppable_pawn(
    pawns: int, color: chess.Color, enemy_pawns: int, enemy_king: int, occupied: int, our_move: bool
) -> bool:
    """Rule of the square: is there a passed pawn with a clear path that the enemy king,
    with no pieces to help, cannot catch?"""
    promo_rank = 7 if color == WHITE else 0
    bb = pawns
    while bb:
        lsb = bb & -bb
        sq = lsb.bit_length() - 1
        bb ^= lsb
        if _PASSED_MASK[color][sq] & enemy_pawns or _PATH[color][sq] & occupied:
            continue
        rank = sq >> 3
        to_go = min(5, 7 - rank) if color == WHITE else min(5, rank)  # a pawn's first move can be two squares
        king_dist = max(abs((enemy_king >> 3) - promo_rank), abs((enemy_king & 7) - (sq & 7)))
        if not our_move:
            king_dist -= 1
        if king_dist > to_go:
            return True
    return False


def _endgame_knowledge(board: chess.Board, white_pawns: int, black_pawns: int) -> int:
    """Flat (not tapered) bonuses for things only true in simple endgames."""
    white_king, black_king = board.king(WHITE), board.king(BLACK)
    if white_king is None or black_king is None:
        return 0
    occ_w, occ_b = board.occupied_co[WHITE], board.occupied_co[BLACK]
    pieces = board.knights | board.bishops | board.rooks | board.queens
    white_pieces, black_pieces = pieces & occ_w, pieces & occ_b
    score = 0

    if not black_pieces and _unstoppable_pawn(
        white_pawns, WHITE, black_pawns, black_king, board.occupied, board.turn == WHITE
    ):
        score += W.UNSTOPPABLE_PAWN_BONUS
    if not white_pieces and _unstoppable_pawn(
        black_pawns, BLACK, white_pawns, white_king, board.occupied, board.turn == BLACK
    ):
        score -= W.UNSTOPPABLE_PAWN_BONUS

    rank_diff = abs((white_king >> 3) - (black_king >> 3))
    file_diff = abs((white_king & 7) - (black_king & 7))

    # Pawn endings: the direct opposition belongs to the side that is NOT to move.
    if not pieces and ((rank_diff == 2 and file_diff == 0) or (rank_diff == 0 and file_diff == 2)):
        score += W.OPPOSITION_BONUS if board.turn == BLACK else -W.OPPOSITION_BONUS

    # Mating a bare king: push it to the edge and bring our own king close.
    majors = board.rooks | board.queens
    minors = board.knights | board.bishops
    for sign, ours, theirs, their_king in ((1, occ_w, black_pieces, black_king), (-1, occ_b, white_pieces, white_king)):
        if not theirs and (majors & ours or (minors & ours).bit_count() >= 2):
            rank, file = their_king >> 3, their_king & 7
            edge = max(3 - min(rank, 7 - rank), 0) + max(3 - min(file, 7 - file), 0)
            closeness = 7 - max(rank_diff, file_diff)
            score += sign * (edge * W.KING_TO_EDGE_BONUS + closeness * W.KING_APPROACH_BONUS)

    return score


def evaluate(board: chess.Board) -> int:
    """Centipawns from White's point of view."""
    occ_w, occ_b = board.occupied_co[WHITE], board.occupied_co[BLACK]
    pawns, knights, bishops = board.pawns, board.knights, board.bishops
    rooks, queens, kings = board.rooks, board.queens, board.kings
    white_pawns, black_pawns = pawns & occ_w, pawns & occ_b

    # Material and piece-square tables.
    packed = 0
    for own, tables in ((occ_w, _PIECE[WHITE]), (occ_b, _PIECE[BLACK])):
        for piece_type, pieces in ((1, pawns), (2, knights), (3, bishops), (4, rooks), (5, queens), (6, kings)):
            bb = pieces & own
            if bb:
                table = tables[piece_type]
                while bb:
                    lsb = bb & -bb
                    packed += table[lsb.bit_length() - 1]
                    bb ^= lsb

    packed += _pawn_structure(white_pawns, black_pawns)
    if rooks:
        packed += _rooks(rooks & occ_w, rooks & occ_b, white_pawns, black_pawns)
    if bishops:
        if (bishops & occ_w).bit_count() >= 2:
            packed += _BISHOP_PAIR
        if (bishops & occ_b).bit_count() >= 2:
            packed -= _BISHOP_PAIR

    mg, eg = _unpack(packed)
    white_king, black_king = board.king(WHITE), board.king(BLACK)
    if white_king is not None and black_king is not None:
        mg += _king_shelter(white_king, WHITE, white_pawns) - _king_shelter(black_king, BLACK, black_pawns)

    phase = min(
        W.PHASE_MAX,
        knights.bit_count() + bishops.bit_count() + 2 * rooks.bit_count() + 4 * queens.bit_count(),
    )
    score = _blend(mg, eg, phase)

    if phase <= 8:
        score += _endgame_knowledge(board, white_pawns, black_pawns)
        # Ahead but with no pawns and less than a rook's worth of extra pieces: usually a draw.
        if score > 0 and not white_pawns and _piece_edge(board, WHITE) < W.PAWNLESS_WIN_MARGIN:
            score = score // 4
        elif score < 0 and not black_pawns and _piece_edge(board, BLACK) < W.PAWNLESS_WIN_MARGIN:
            score = -(-score // 4)

    return score + W.TEMPO if board.turn == WHITE else score - W.TEMPO


def _piece_edge(board: chess.Board, color: chess.Color) -> int:
    """`color`'s non-pawn material minus the opponent's, in endgame piece values."""
    ours, theirs = board.occupied_co[color], board.occupied_co[not color]
    edge = 0
    for piece_type, pieces in ((2, board.knights), (3, board.bishops), (4, board.rooks), (5, board.queens)):
        edge += ((pieces & ours).bit_count() - (pieces & theirs).bit_count()) * W.PIECE_VALUES_EG[piece_type]
    return edge
