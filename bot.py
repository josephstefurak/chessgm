import chess
import time
from evaluator import evaluate, clear_eval_cache

PIECE_VALUES_SIMPLE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

_tt = {}
TT_MAX_SIZE = 1_000_000
REPETITION_PENALTY = 300  # Penalty for repeating a position when winning
NULL_MOVE_REDUCTION = 2   # Null move depth reduction (R)


def material_balance(board):
    """
    Returns material balance from White's perspective in pawns.
    Positive = White is ahead, negative = Black is ahead.
    """
    score = 0
    for color in [chess.WHITE, chess.BLACK]:
        sign = 1 if color == chess.WHITE else -1
        for piece_type, value in PIECE_VALUES_SIMPLE.items():
            score += sign * len(board.pieces(piece_type, color)) * value
    return score


def score_move(board, move):
    score = 0
    if move.promotion:
        score += 900
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)
        if victim and attacker:
            score += 100 + (PIECE_VALUES_SIMPLE[victim.piece_type] * 10 - PIECE_VALUES_SIMPLE[attacker.piece_type])
    board.push(move)
    if board.is_check():
        score += 50
    board.pop()
    return score


def order_moves(board, moves):
    return sorted(moves, key=lambda m: score_move(board, m), reverse=True)


def quiescence(board, alpha, beta, maximizing):
    stand_pat = evaluate(board)

    if maximizing:
        if stand_pat >= beta:
            return beta
        alpha = max(alpha, stand_pat)
    else:
        if stand_pat <= alpha:
            return alpha
        beta = min(beta, stand_pat)

    captures = [m for m in board.legal_moves if board.is_capture(m)]
    captures = order_moves(board, captures)

    for move in captures:
        board.push(move)
        try:
            score = quiescence(board, alpha, beta, not maximizing)
        finally:
            board.pop()

        if maximizing:
            alpha = max(alpha, score)
            if alpha >= beta:
                return beta
        else:
            beta = min(beta, score)
            if beta <= alpha:
                return alpha

    return alpha if maximizing else beta


def minimax(board, depth, alpha, beta, maximizing, deadline=None):
    if deadline and time.time() > deadline:
        raise TimeoutError()

    # --- Repetition detection ---
    # If this position has been seen before and we're winning, treat it as bad
    if board.is_repetition(2):
        mat = material_balance(board)
        # If the side to move is winning, penalize repetition heavily
        if maximizing and mat < -1:   # Black (bot) is winning
            return -REPETITION_PENALTY
        if not maximizing and mat > 1: # White (bot) is winning
            return REPETITION_PENALTY

    orig_alpha = alpha
    key = board._transposition_key()

    if key in _tt:
        tt_score, tt_depth, tt_flag = _tt[key]
        if tt_depth >= depth:
            if tt_flag == 'exact':
                return tt_score
            elif tt_flag == 'lower':
                alpha = max(alpha, tt_score)
            elif tt_flag == 'upper':
                beta = min(beta, tt_score)
            if alpha >= beta:
                return tt_score

    if board.is_game_over():
        return evaluate(board)

    if depth == 0:
        return quiescence(board, alpha, beta, maximizing)

    # --- Null move pruning ---
    if depth >= 3 and not board.is_check():
        board.push(chess.Move.null())
        try:
            null_score = minimax(board, depth - 1 - NULL_MOVE_REDUCTION,
                                 -beta, -beta + 1, not maximizing, deadline)
            null_score = -null_score
        finally:
            board.pop()
        if null_score >= beta:
            return beta

    legal_moves = order_moves(board, list(board.legal_moves))
    best_score = float("-inf") if maximizing else float("inf")

    for move in legal_moves:
        board.push(move)
        try:
            # --- Stalemate avoidance ---
            if board.is_stalemate():
                mat = material_balance(board)
                if (not maximizing and mat < -2) or (maximizing and mat > 2):
                    continue

            score = minimax(board, depth - 1, alpha, beta, not maximizing, deadline)
        finally:
            board.pop()

        if maximizing:
            best_score = max(best_score, score)
            alpha = max(alpha, score)
        else:
            best_score = min(best_score, score)
            beta = min(beta, score)

        if beta <= alpha:
            break

    if best_score <= orig_alpha:
        flag = 'upper'
    elif best_score >= beta:
        flag = 'lower'
    else:
        flag = 'exact'

    if len(_tt) < TT_MAX_SIZE:
        _tt[key] = (best_score, depth, flag)

    return best_score


def get_best_move(board, depth=5):
    """Fixed depth search — used for training and local play."""
    _tt.clear()
    clear_eval_cache()
    best_move = None
    maximizing = board.turn == chess.BLACK
    best_score = float("-inf") if maximizing else float("inf")

    for move in order_moves(board, list(board.legal_moves)):
        board.push(move)
        try:
            score = minimax(board, depth - 1, float("-inf"), float("inf"), not maximizing)
        finally:
            board.pop()

        if maximizing and score > best_score:
            best_score = score
            best_move = move
        elif not maximizing and score < best_score:
            best_score = score
            best_move = move

    return best_move


def get_best_move_timed(board, move_time):
    """
    Iterative deepening with time management.
    Searches depth 1, 2, 3... until move_time seconds runs out.
    Always returns the best move found so far, so it never times out.
    """
    _tt.clear()
    clear_eval_cache()
    deadline = time.time() + move_time
    maximizing = board.turn == chess.BLACK
    best_move = list(board.legal_moves)[0]  # fallback

    for depth in range(1, 20):
        try:
            candidate_move = None
            candidate_score = float("-inf") if maximizing else float("inf")

            for move in order_moves(board, list(board.legal_moves)):
                board.push(move)
                try:
                    score = minimax(board, depth - 1, float("-inf"), float("inf"), not maximizing, deadline)
                finally:
                    board.pop()

                if maximizing and score > candidate_score:
                    candidate_score = score
                    candidate_move = move
                elif not maximizing and score < candidate_score:
                    candidate_score = score
                    candidate_move = move

            if candidate_move:
                best_move = candidate_move

        except TimeoutError:
            break

    return best_move