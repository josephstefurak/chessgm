"""Search: iterative deepening negamax with alpha-beta.

Conventions
-----------
* Every score is from the point of view of the side to move (negamax).
  `engine.evaluation.evaluate` is White-relative and is flipped here.
* Mate scores are `MATE - ply`, so a faster mate always scores higher.
* Draws (repetition, 50-move rule, insufficient material, stalemate) score 0.
* The search never prints. Progress is reported through the `on_info` callback.

The search mutates the board it is given while it runs and always restores it
before returning, including when it is stopped or runs out of time.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import chess

from engine.evaluation import evaluate

MATE = 30_000
MATE_BOUND = MATE - 1_000  # any score beyond this is a forced mate
INFINITY = 32_000
MAX_PLY = 96
MAX_DEPTH = 64

EXACT, LOWER, UPPER = 0, 1, 2

# Simple piece values used only for ordering and pruning decisions (index = piece type).
ORDER_VALUE = (0, 100, 320, 330, 500, 900, 20_000)

TT_MOVE_SCORE = 10_000_000
CAPTURE_SCORE = 1_000_000
PROMOTION_SCORE = 900_000
KILLER_SCORE = 800_000
HISTORY_MAX = 700_000

QUIESCENCE_MAX_PLY = 10  # how many capture plies quiescence may chain
DELTA_MARGIN = 200  # quiescence: skip captures that cannot get within this of alpha
ABORT_CHECK_MASK = 255  # look at the clock every 256 nodes


@dataclass(frozen=True)
class SearchConfig:
    """Switches for the pruning and reduction techniques, so each can be A/B tested."""

    null_move: bool = True
    late_move_reductions: bool = True
    reverse_futility: bool = True
    futility: bool = True
    aspiration: bool = True
    check_extension: bool = True
    bad_capture_pruning: bool = True
    late_move_pruning: bool = True


@dataclass(frozen=True)
class Limits:
    """When to stop. Any field left as None is not a limit."""

    soft_time: float | None = None  # seconds: do not start another depth after this
    hard_time: float | None = None  # seconds: abandon the search at this point
    depth: int | None = None
    nodes: int | None = None


@dataclass(frozen=True)
class SearchInfo:
    depth: int
    score: int
    nodes: int
    seconds: float
    pv: list[chess.Move]

    @property
    def mate_in(self) -> int | None:
        """Moves until mate (negative if we are the one being mated), or None."""
        return mate_in_moves(self.score)


@dataclass(frozen=True)
class SearchResult:
    move: chess.Move
    score: int
    depth: int  # last depth that was searched to completion
    nodes: int
    seconds: float
    pv: list[chess.Move] = field(default_factory=list)

    @property
    def mate_in(self) -> int | None:
        return mate_in_moves(self.score)


def mate_in_moves(score: int) -> int | None:
    if score >= MATE_BOUND:
        return (MATE - score + 1) // 2
    if score <= -MATE_BOUND:
        return -((MATE + score + 1) // 2)
    return None


class _Abort(Exception):
    """Raised inside the search when time is up or a stop was requested."""


def position_key(board: chess.Board) -> int:
    """Identity of a position for the transposition table and repetition checks.

    Built from the raw bitboards rather than `Board._transposition_key()`, which does
    extra work (cleaning castling rights, testing en passant legality) on every call
    and is about four times slower. Black's occupancy is implied by the piece boards
    minus White's, so it is left out.
    """
    return hash(
        (
            board.pawns,
            board.knights,
            board.bishops,
            board.rooks,
            board.queens,
            board.kings,
            board.occupied_co[True],
            board.turn,
            board.castling_rights,
            board.ep_square,
        )
    )


def _move_id(move: chess.Move) -> int:
    """Pack a move into an int: from, to, promotion. Never 0 for a real move."""
    packed = move.from_square | (move.to_square << 6)
    if move.promotion:
        packed |= move.promotion << 12
    return packed


class Searcher:
    """Holds everything that persists between searches in one game: the
    transposition table, the history heuristic and the eval cache."""

    def __init__(self, config: SearchConfig | None = None, tt_entries: int = 400_000) -> None:
        self.config = config or SearchConfig()
        self.tt_max = max(1_000, tt_entries)
        # key -> (depth, flag, score, move_id)
        self.tt: dict[int, tuple[int, int, int, int]] = {}
        self.eval_cache: dict[int, int] = {}
        self.history: list[list[int]] = [[0] * 4096, [0] * 4096]
        self.killers: list[list[int]] = [[0, 0] for _ in range(MAX_PLY + 2)]
        self.stop_event = threading.Event()
        self.nodes = 0

        self._keys: list[int] = []  # position keys from the game start to the current node
        self._rep_floor = 0  # repetition lookback may not cross this index (null moves)
        self._deadline: float | None = None
        self._node_limit: int | None = None
        self._can_abort = False
        self._root_best: tuple[chess.Move, int] | None = None
        # Late move reduction table: how much to reduce by depth and move number.
        self._lmr = [
            [int(0.75 + math.log(d) * math.log(m) / 2.25) if d and m else 0 for m in range(64)]
            for d in range(MAX_DEPTH + 1)
        ]

    # ------------------------------------------------------------------ setup

    def new_game(self) -> None:
        self.tt.clear()
        self.eval_cache.clear()
        self.history = [[0] * 4096, [0] * 4096]

    def stop(self) -> None:
        """Ask a running search to finish as soon as possible. Safe from another thread."""
        self.stop_event.set()

    # ------------------------------------------------------------------- root

    def search(
        self,
        board: chess.Board,
        limits: Limits,
        on_info: Callable[[SearchInfo], None] | None = None,
    ) -> SearchResult:
        """Pick a move for the side to move. Raises ValueError if the game is over."""
        start = time.perf_counter()
        root_moves = list(board.legal_moves)
        if not root_moves:
            raise ValueError("no legal moves: the game is over")

        self.stop_event.clear()
        self.nodes = 0
        self._deadline = start + limits.hard_time if limits.hard_time is not None else None
        self._node_limit = limits.nodes
        self.killers = [[0, 0] for _ in range(MAX_PLY + 2)]
        for table in self.history:  # age, so old games' habits fade
            for i, value in enumerate(table):
                if value:
                    table[i] = value >> 2
        self._keys = self._game_keys(board)
        self._rep_floor = 0

        root_stack = len(board.move_stack)
        root_keys = len(self._keys)
        best_move = root_moves[0]
        best_score = 0
        completed = 0
        pv: list[chess.Move] = [best_move]
        max_depth = min(limits.depth or MAX_DEPTH, MAX_DEPTH)
        timed = limits.soft_time is not None or limits.hard_time is not None

        try:
            for depth in range(1, max_depth + 1):
                # Depth 1 always runs to completion, so the move returned has always
                # been searched, however small the time budget.
                self._can_abort = depth > 1
                self._root_best = None
                score = self._search_root(board, depth, best_score)
                if self._root_best is not None:
                    best_move, best_score = self._root_best[0], score
                completed = depth
                pv = self._principal_variation(board, best_move, depth)
                elapsed = time.perf_counter() - start
                if on_info is not None:
                    on_info(SearchInfo(depth, best_score, self.nodes, elapsed, pv))

                if len(root_moves) == 1 and timed:
                    break  # nothing to choose between: do not spend clock on it
                mate = mate_in_moves(best_score)
                if mate is not None and depth >= 2 * abs(mate) + 2:
                    break  # mate is proven and deeper search cannot shorten it much
                if limits.soft_time is not None and elapsed >= limits.soft_time:
                    break
                if self.stop_event.is_set():
                    break
        except _Abort:
            # An unfinished depth still counts if it found a move that beat the previous
            # best: the previous best is always searched first at the new depth.
            if self._root_best is not None:
                best_move, best_score = self._root_best
                pv = [best_move]
        finally:
            while len(board.move_stack) > root_stack:
                board.pop()
            del self._keys[root_keys:]

        return SearchResult(best_move, best_score, completed, self.nodes, time.perf_counter() - start, pv)

    def _search_root(self, board: chess.Board, depth: int, previous: int) -> int:
        """One iteration, with an aspiration window around the previous score."""
        if not self.config.aspiration or depth < 4 or abs(previous) >= MATE_BOUND:
            return self._negamax(board, depth, -INFINITY, INFINITY, 0, False)
        window = 40
        alpha, beta = previous - window, previous + window
        while True:
            score = self._negamax(board, depth, alpha, beta, 0, False)
            if score <= alpha:
                alpha = max(-INFINITY, alpha - window)
            elif score >= beta:
                beta = min(INFINITY, beta + window)
            else:
                return score
            window *= 3
            if window > 1_000:
                alpha, beta = -INFINITY, INFINITY

    def _game_keys(self, board: chess.Board) -> list[int]:
        """Keys of every earlier position in the game, oldest first (for repetition)."""
        replay = board.root()
        keys: list[int] = []
        for move in board.move_stack:
            keys.append(position_key(replay))
            replay.push(move)
        return keys

    def _principal_variation(self, board: chess.Board, first: chess.Move, depth: int) -> list[chess.Move]:
        """Follow best moves through the transposition table."""
        pv = [first]
        board.push(first)
        pushed = 1
        seen: set[int] = set()
        try:
            while len(pv) < depth:
                key = position_key(board)
                entry = self.tt.get(key)
                if entry is None or not entry[3] or key in seen:
                    break
                seen.add(key)
                move = next((m for m in board.legal_moves if _move_id(m) == entry[3]), None)
                if move is None:
                    break
                pv.append(move)
                board.push(move)
                pushed += 1
        finally:
            for _ in range(pushed):
                board.pop()
        return pv

    # ----------------------------------------------------------------- helpers

    def _check_abort(self) -> None:
        if not self._can_abort:
            return
        if self.stop_event.is_set():
            raise _Abort
        if self._deadline is not None and time.perf_counter() >= self._deadline:
            raise _Abort
        if self._node_limit is not None and self.nodes >= self._node_limit:
            raise _Abort

    def _static_eval(self, board: chess.Board, key: int) -> int:
        """Evaluation from the side to move's point of view, cached by position."""
        cached = self.eval_cache.get(key)
        if cached is None:
            cached = evaluate(board)
            if len(self.eval_cache) >= self.tt_max:
                self.eval_cache.clear()
            self.eval_cache[key] = cached
        return cached if board.turn else -cached

    def _is_repetition(self, key: int, halfmove_clock: int) -> bool:
        """Has this position already occurred since the last capture or pawn move?"""
        if halfmove_clock < 4:
            return False
        keys = self._keys
        end = len(keys)
        start = max(self._rep_floor, end - halfmove_clock)
        # Same side to move is every second ply back; the closest candidate is 4 plies ago.
        for i in range(end - 4, start - 1, -2):
            if keys[i] == key:
                return True
        return False

    def _order(self, board: chess.Board, moves: list[chess.Move], tt_move: int, ply: int) -> list[chess.Move]:
        """Best-first: hash move, winning captures, promotions, killers, then history."""
        turn = board.turn
        enemy = board.occupied_co[not turn]
        ep_square = board.ep_square
        history = self.history[turn]
        killer_a, killer_b = self.killers[ply] if ply <= MAX_PLY else (0, 0)
        piece_type_at = board.piece_type_at
        scored: list[tuple[int, int, chess.Move]] = []
        for index, move in enumerate(moves):
            frm, to = move.from_square, move.to_square
            packed = frm | (to << 6)
            promotion = move.promotion
            if promotion:
                packed |= promotion << 12
            if packed == tt_move:
                score = TT_MOVE_SCORE
            elif (enemy >> to) & 1:
                score = CAPTURE_SCORE + 16 * ORDER_VALUE[piece_type_at(to) or 0] - ORDER_VALUE[piece_type_at(frm) or 0]
                if promotion == chess.QUEEN:
                    score += PROMOTION_SCORE
            elif to == ep_square and piece_type_at(frm) == chess.PAWN and (frm & 7) != (to & 7):
                score = CAPTURE_SCORE + 15 * ORDER_VALUE[chess.PAWN]
            elif promotion:
                score = PROMOTION_SCORE if promotion == chess.QUEEN else -1
            elif packed == killer_a:
                score = KILLER_SCORE
            elif packed == killer_b:
                score = KILLER_SCORE - 1
            else:
                score = history[packed & 4095]
            scored.append((score, -index, move))
        scored.sort(reverse=True)
        return [entry[2] for entry in scored]

    # ------------------------------------------------------------------ search

    def _negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int, can_null: bool) -> int:
        self.nodes += 1
        if not self.nodes & ABORT_CHECK_MASK:
            self._check_abort()

        cfg = self.config
        is_pv = beta - alpha > 1
        key = position_key(board)
        in_check = board.is_check()

        if ply > 0:
            if board.halfmove_clock >= 100:
                # Checkmate delivered on the 100th ply still counts as mate.
                if in_check and not any(board.generate_legal_moves()):
                    return -MATE + ply
                return 0
            if self._is_repetition(key, board.halfmove_clock) or board.is_insufficient_material():
                return 0
            # Mate distance pruning: no line from here can beat a mate already found.
            alpha = max(alpha, -MATE + ply)
            beta = min(beta, MATE - ply - 1)
            if alpha >= beta:
                return alpha
            if ply >= MAX_PLY:
                return self._static_eval(board, key)

        if in_check and cfg.check_extension:
            depth += 1
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply, 0)

        tt_move = 0
        entry = self.tt.get(key)
        if entry is not None:
            tt_depth, tt_flag, tt_score, tt_move = entry
            if tt_depth >= depth and not is_pv and ply > 0:
                # Mate scores are stored relative to the node; make them relative to the root.
                if tt_score >= MATE_BOUND:
                    tt_score -= ply
                elif tt_score <= -MATE_BOUND:
                    tt_score += ply
                if tt_flag == EXACT or (tt_flag == LOWER and tt_score >= beta) or (tt_flag == UPPER and tt_score <= alpha):
                    return tt_score

        static = 0
        prunable = not is_pv and not in_check and ply > 0
        if prunable or (cfg.futility and not in_check and depth <= 2):
            static = self._static_eval(board, key)

        if prunable and abs(beta) < MATE_BOUND:
            # Reverse futility: already so far above beta that a shallow search will not drop below it.
            if cfg.reverse_futility and depth <= 3 and static - 120 * depth >= beta:
                return static
            # Null move: give the opponent a free move; if we are still above beta, prune.
            # Skipped with only king and pawns, where being forced to move can be fatal (zugzwang).
            if (
                cfg.null_move
                and can_null
                and depth >= 3
                and static >= beta
                and board.occupied_co[board.turn] & ~(board.pawns | board.kings)
            ):
                reduction = 2 + depth // 4
                board.push(chess.Move.null())
                self._keys.append(key)
                saved_floor = self._rep_floor
                self._rep_floor = len(self._keys)
                score = -self._negamax(board, depth - 1 - reduction, -beta, -beta + 1, ply + 1, False)
                self._rep_floor = saved_floor
                self._keys.pop()
                board.pop()
                if score >= beta:
                    return beta if score >= MATE_BOUND else score

        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply if in_check else 0
        moves = self._order(board, moves, tt_move, ply)

        futile = (
            cfg.futility
            and not is_pv
            and not in_check
            and depth <= 2
            and abs(alpha) < MATE_BOUND
            and static + 150 * depth <= alpha
        )
        # Late move pruning: near the leaves, quiet moves this far down a well-ordered list
        # almost never matter, so only the first few are searched.
        quiet_limit = 4 + 3 * depth * depth if cfg.late_move_pruning and prunable and depth <= 3 else 1_000
        quiets_seen = 0
        enemy = board.occupied_co[not board.turn]
        ep_square = board.ep_square
        best = -INFINITY
        best_move = 0
        flag = UPPER
        original_alpha = alpha
        self._keys.append(key)

        for index, move in enumerate(moves):
            to = move.to_square
            quiet = not ((enemy >> to) & 1) and not move.promotion and to != ep_square
            board.push(move)
            gives_check = board.is_check()

            if quiet and not gives_check and index > 0:
                quiets_seen += 1
                # Futility: a quiet, non-checking move this far below alpha will not rescue the node.
                if futile or (quiets_seen > quiet_limit and best > -MATE_BOUND):
                    board.pop()
                    continue

            if index == 0:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1, True)
            else:
                reduction = 0
                if (
                    cfg.late_move_reductions
                    and depth >= 3
                    and index >= (4 if is_pv else 3)
                    and quiet
                    and not in_check
                    and not gives_check
                ):
                    reduction = self._lmr[min(depth, MAX_DEPTH)][min(index, 63)]
                    if is_pv and reduction > 0:
                        reduction -= 1
                    reduction = min(reduction, depth - 2)
                # Zero-window probe: we only want to know whether it beats alpha.
                score = -self._negamax(board, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1, True)
                if score > alpha and reduction > 0:
                    score = -self._negamax(board, depth - 1, -alpha - 1, -alpha, ply + 1, True)
                if alpha < score < beta:
                    score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1, True)
            board.pop()

            if score > best:
                best = score
                best_move = _move_id(move)
                if score > alpha:
                    alpha = score
                    flag = EXACT
                    if ply == 0:
                        self._root_best = (move, score)
                    if alpha >= beta:
                        flag = LOWER
                        if quiet:
                            killers = self.killers[ply] if ply <= MAX_PLY else [0, 0]
                            if killers[0] != best_move:
                                killers[1] = killers[0]
                                killers[0] = best_move
                            table = self.history[board.turn]
                            slot = best_move & 4095
                            table[slot] = min(HISTORY_MAX, table[slot] + depth * depth)
                        break

        self._keys.pop()

        if best == -INFINITY:
            # Every move was pruned as futile: the node cannot reach alpha.
            return original_alpha

        stored = best
        if stored >= MATE_BOUND:
            stored += ply
        elif stored <= -MATE_BOUND:
            stored -= ply
        if len(self.tt) >= self.tt_max and key not in self.tt:
            self.tt.clear()
        self.tt[key] = (depth, flag, stored, best_move)
        return best

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, ply: int, qply: int) -> int:
        """Play out captures until the position is quiet, so the static eval is
        never taken in the middle of an exchange."""
        self.nodes += 1
        if not self.nodes & ABORT_CHECK_MASK:
            self._check_abort()

        key = position_key(board)
        in_check = board.is_check()
        if in_check:
            # No standing pat while in check: every evasion must be looked at.
            moves = list(board.legal_moves)
            if not moves:
                return -MATE + ply
            best = -INFINITY
            stand = -INFINITY
            if qply >= QUIESCENCE_MAX_PLY or ply >= MAX_PLY:
                return self._static_eval(board, key)
        else:
            stand = self._static_eval(board, key)
            if stand >= beta:
                return stand
            if qply >= QUIESCENCE_MAX_PLY or ply >= MAX_PLY:
                return stand
            alpha = max(alpha, stand)
            best = stand
            # Captures, with underpromotions dropped: they are never better than queening here.
            moves = [
                m for m in board.generate_legal_captures() if not m.promotion or m.promotion == chess.QUEEN
            ]
            # Quiet queen promotions change the material balance as much as a capture does.
            promoting = board.pawns & board.occupied_co[board.turn] & (chess.BB_RANK_7 if board.turn else chess.BB_RANK_2)
            if promoting:
                moves.extend(
                    m
                    for m in board.generate_legal_moves(promoting, chess.BB_ALL & ~board.occupied)
                    if m.promotion == chess.QUEEN
                )
            if not moves:
                return stand

        moves = self._order(board, moves, 0, MAX_PLY + 1)
        piece_type_at = board.piece_type_at
        prune_bad = self.config.bad_capture_pruning
        enemy_pawns = board.pawns & board.occupied_co[not board.turn]

        for move in moves:
            if not in_check:
                to = move.to_square
                victim = ORDER_VALUE[piece_type_at(to) or chess.PAWN]
                gain = victim + (ORDER_VALUE[chess.QUEEN] - 100 if move.promotion else 0)
                # Delta pruning: even winning this piece for free cannot reach alpha.
                if stand + gain + DELTA_MARGIN <= alpha:
                    continue
                # A piece taking a cheaper one on a pawn-defended square just loses material.
                if (
                    prune_bad
                    and not move.promotion
                    and ORDER_VALUE[piece_type_at(move.from_square) or 0] > victim + 50
                    and chess.BB_PAWN_ATTACKS[board.turn][to] & enemy_pawns
                ):
                    continue
            board.push(move)
            score = -self._quiesce(board, -beta, -alpha, ply + 1, qply + 1)
            board.pop()
            if score > best:
                best = score
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        return best
