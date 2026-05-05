import chess
import time
from evaluator import evaluate

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
        score = quiescence(board, alpha, beta, not maximizing)
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
    # Check time — abort search if deadline exceeded
    if deadline and time.time() > deadline:
        raise TimeoutError()

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

    legal_moves = order_moves(board, list(board.legal_moves))
    best_score = float("-inf") if maximizing else float("inf")

    for move in legal_moves:
        board.push(move)
        score = minimax(board, depth - 1, alpha, beta, not maximizing, deadline)
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
    best_move = None
    maximizing = board.turn == chess.BLACK
    best_score = float("-inf") if maximizing else float("inf")

    for move in order_moves(board, list(board.legal_moves)):
        board.push(move)
        score = minimax(board, depth - 1, float("-inf"), float("inf"), not maximizing)
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
    Used by uci.py for Lichess games.
    """
    _tt.clear()
    deadline = time.time() + move_time
    maximizing = board.turn == chess.BLACK
    best_move = list(board.legal_moves)[0]  # fallback

    for depth in range(1, 20):
        try:
            candidate_move = None
            candidate_score = float("-inf") if maximizing else float("inf")

            for move in order_moves(board, list(board.legal_moves)):
                board.push(move)
                score = minimax(board, depth - 1, float("-inf"), float("inf"), not maximizing, deadline)
                board.pop()

                if maximizing and score > candidate_score:
                    candidate_score = score
                    candidate_move = move
                elif not maximizing and score < candidate_score:
                    candidate_score = score
                    candidate_move = move

            # Only update best_move if we completed the full depth search
            if candidate_move:
                best_move = candidate_move

        except TimeoutError:
            # Time ran out mid-search — return the best move from the last completed depth
            break

    return best_move