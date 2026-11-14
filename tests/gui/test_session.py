"""The game session: every rule the GUI enforces, with a manual engine and a fake clock."""

from __future__ import annotations

import chess
import pytest

from engine import timeman
from engine.search import MATE, Limits, SearchInfo
from tests.gui.fakes import make_session, play
from webgui.server.session import Conflict, Rejected

SCHOLARS_MATE = "e2e4 g7g5 d1h5 h7h6 f1c4 a7a6 h5f7"
TO_PROMOTION = "h2h4 g7g5 h4g5 h7h6 g5h6 a7a6 h6h7 a6a5"


def move(uci: str) -> chess.Move:
    return chess.Move.from_uci(uci)


# ------------------------------------------------------------------ basic play


def test_a_fresh_session_is_ready_to_play_as_white() -> None:
    session, engine, _ = make_session()
    state = session.snapshot()
    assert (state.human, state.turn, state.status, state.result) == ("white", "white", "playing", None)
    assert state.plies == []
    assert sum(len(targets) for targets in state.legal.dests.values()) == 20
    assert state.legal.dests["g1"] == ["h3", "f3"]
    assert state.legal.promotions == []
    assert (state.actions.takeback, state.actions.resign) == (False, True)
    assert state.engine.state == "idle"
    assert state.clock is None and state.time_control is None
    assert [control.id for control in state.time_controls] == ["3+2", "5+3", "10+0", "15+10"]
    assert engine.pending is None


def test_a_human_move_is_recorded_and_the_engine_is_asked() -> None:
    session, engine, _ = make_session()
    start = session.snapshot()
    state = session.move(start.game_id, 0, "e2e4")
    assert [(ply.ply, ply.san, ply.uci) for ply in state.plies] == [(1, "e4", "e2e4")]
    assert state.plies[0].fen == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    assert state.turn == "black"
    assert state.legal.dests == {}  # not the human's turn: nothing may be moved
    assert state.engine.state == "thinking"
    assert state.version > start.version
    assert engine.pending is not None
    assert engine.pending.board.fen() == state.plies[0].fen


def test_the_engine_reply_hands_the_turn_back() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 e7e5")
    state = session.snapshot()
    assert [ply.san for ply in state.plies] == ["e4", "e5"]
    assert state.turn == "white"
    assert state.engine.state == "idle"
    assert "e4" in state.legal.dests["d1"] or state.legal.dests["d1"]  # the queen can move now
    assert state.actions.takeback is True


def test_playing_black_the_engine_moves_first() -> None:
    session, engine, _ = make_session(human="black")
    state = session.snapshot()
    assert (state.human, state.turn, state.engine.state) == ("black", "white", "thinking")
    assert state.actions.takeback is False
    engine.reply("d2d4")
    state = session.snapshot()
    assert [ply.san for ply in state.plies] == ["d4"]
    assert state.turn == "black" and "d7" in state.legal.dests


def test_random_colour_is_decided_by_the_generator() -> None:
    session, _, _ = make_session()
    seen = {session.new_game("random", None).human for _ in range(20)}
    assert seen == {"white", "black"}


def test_new_game_resets_everything_and_tells_the_engine() -> None:
    session, engine, _ = make_session()
    first = session.snapshot()
    play(session, engine, "e2e4 e7e5")
    state = session.new_game("white", "5+3")
    assert state.game_id != first.game_id
    assert state.plies == [] and state.time_control == "5+3"
    assert engine.new_games == 2  # once at start-up, once now


# ------------------------------------------------------------------- refusals


def test_an_illegal_move_is_rejected_and_changes_nothing() -> None:
    session, _, _ = make_session()
    before = session.snapshot()
    with pytest.raises(Rejected) as caught:
        session.move(before.game_id, 0, "e2e5")
    assert caught.value.code == "illegal_move"
    assert session.snapshot() == before


def test_stale_requests_are_conflicts() -> None:
    session, engine, _ = make_session()
    start = session.snapshot()
    play(session, engine, "e2e4 e7e5")
    with pytest.raises(Conflict) as stale_position:
        session.move(start.game_id, 0, "d2d4")
    assert stale_position.value.code == "stale_position"
    with pytest.raises(Conflict) as stale_game:
        session.move("0" * 16, 2, "d2d4")
    assert stale_game.value.code == "stale_game"
    assert len(session.snapshot().plies) == 2


def test_the_human_cannot_move_for_the_engine() -> None:
    session, _, _ = make_session()
    state = session.move(session.snapshot().game_id, 0, "e2e4")
    with pytest.raises(Conflict) as caught:
        session.move(state.game_id, 1, "e7e5")
    assert caught.value.code == "not_your_turn"


def test_unknown_time_control_is_rejected() -> None:
    session, _, _ = make_session()
    with pytest.raises(Rejected) as caught:
        session.new_game("white", "1+1")
    assert caught.value.code == "unknown_time_control"


# ------------------------------------------------------------- special moves


def test_promotion_needs_a_piece_and_is_listed_for_the_browser() -> None:
    session, engine, _ = make_session()
    play(session, engine, TO_PROMOTION)
    state = session.snapshot()
    assert state.legal.promotions == ["h7g8"]
    assert state.legal.dests["h7"] == ["g8"]
    with pytest.raises(Rejected):
        session.move(state.game_id, len(state.plies), "h7g8")
    state = session.move(state.game_id, len(state.plies), "h7g8n")
    assert state.plies[-1].san == "hxg8=N"
    assert state.plies[-1].capture is True


def test_en_passant_removes_the_captured_pawn() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 a7a6 e4e5 d7d5 e5d6")
    last = session.snapshot().plies[-1]
    assert (last.san, last.capture) == ("exd6", True)
    assert last.fen.split()[0] == "rnbqkbnr/1pp1pppp/p2P4/8/8/8/PPPP1PPP/RNBQKBNR"


def test_castling_is_sent_as_a_king_move() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 a7a6 g1f3 a6a5 f1c4 a5a4")
    state = session.snapshot()
    assert "g1" in state.legal.dests["e1"]
    state = session.move(state.game_id, len(state.plies), "e1g1")
    assert state.plies[-1].san == "O-O"


def test_check_names_the_side_in_check() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 f7f6 d1h5")
    plies = session.snapshot().plies
    assert [ply.check for ply in plies] == [None, None, "black"]
    assert plies[-1].san == "Qh5+"


# ------------------------------------------------------------------ game end


def test_checkmate_ends_the_game_and_the_engine_is_not_asked() -> None:
    session, engine, _ = make_session()
    play(session, engine, SCHOLARS_MATE)
    state = session.snapshot()
    assert state.status == "finished"
    assert state.result is not None
    assert (state.result.winner, state.result.reason) == ("white", "checkmate")
    assert state.plies[-1].san == "Qxf7#"
    assert state.legal.dests == {}
    assert (state.actions.takeback, state.actions.resign) == (False, False)
    assert engine.pending is None
    with pytest.raises(Conflict) as caught:
        session.move(state.game_id, len(state.plies), "a2a3")
    assert caught.value.code == "game_over"


def test_threefold_repetition_is_an_automatic_draw() -> None:
    session, engine, _ = make_session()
    play(session, engine, "g1f3 g8f6 f3g1 f6g8 g1f3 g8f6 f3g1 f6g8")
    result = session.snapshot().result
    assert result is not None
    assert (result.winner, result.reason) == (None, "threefold_repetition")


def test_resigning_gives_the_engine_the_game() -> None:
    session, engine, _ = make_session()
    state = session.move(session.snapshot().game_id, 0, "e2e4")
    thinking = engine.pending
    assert thinking is not None
    state = session.resign(state.game_id)
    assert state.result is not None
    assert (state.result.winner, state.result.reason) == ("black", "resignation")
    assert state.engine.state == "idle"
    thinking.reply("e7e5")  # an answer that arrives after the game ended is dropped
    assert len(session.snapshot().plies) == 1
    with pytest.raises(Conflict):
        session.resign(state.game_id)


# ------------------------------------------------------------------ takeback


def test_takeback_on_your_turn_undoes_both_moves() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 e7e5 g1f3 b8c6")
    state = session.snapshot()
    state = session.takeback(state.game_id, 4)
    assert [ply.san for ply in state.plies] == ["e4", "e5"]
    assert state.turn == "white" and state.legal.dests


def test_takeback_while_the_engine_thinks_undoes_one_move_and_drops_its_answer() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 e7e5 g1f3")
    thinking = engine.pending
    assert thinking is not None
    cancels = engine.cancels
    state = session.takeback(session.snapshot().game_id, 3)
    assert [ply.san for ply in state.plies] == ["e4", "e5"]
    assert state.turn == "white" and state.engine.state == "idle"
    assert engine.cancels == cancels + 1
    thinking.reply("b8c6")  # too late: it answers a position that is gone
    assert len(session.snapshot().plies) == 2


def test_nothing_to_take_back() -> None:
    session, engine, _ = make_session()
    with pytest.raises(Conflict) as caught:
        session.takeback(session.snapshot().game_id, 0)
    assert caught.value.code == "nothing_to_take_back"

    session, engine, _ = make_session(human="black")
    engine.reply("e2e4")
    state = session.snapshot()
    assert state.actions.takeback is False  # only the engine has moved
    with pytest.raises(Conflict):
        session.takeback(state.game_id, 1)


# -------------------------------------------------------------- engine output


def test_scores_are_shown_from_whites_side() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")  # the engine is Black and is to move
    assert engine.pending is not None
    line = [move("e7e5"), move("g1f3"), move("b8c6")]
    engine.pending.on_info(SearchInfo(depth=6, score=50, nodes=12_345, seconds=0.25, pv=line))
    status = session.snapshot().engine
    assert status.state == "thinking"
    assert status.score is not None and (status.score.cp, status.score.mate) == (-50, None)
    assert (status.depth, status.nodes, status.ms, status.ply) == (6, 12_345, 250, 1)
    assert status.pv_san == ["e5", "Nf3", "Nc6"]

    engine.pending.on_info(SearchInfo(depth=7, score=MATE - 3, nodes=1, seconds=0.3, pv=line[:1]))
    score = session.snapshot().engine.score
    assert score is not None and (score.cp, score.mate) == (None, -2)  # Black mates in 2


def test_white_engine_scores_keep_their_sign() -> None:
    session, engine, _ = make_session(human="black")
    assert engine.pending is not None
    engine.pending.on_info(SearchInfo(depth=4, score=30, nodes=1, seconds=0.1, pv=[move("e2e4")]))
    score = session.snapshot().engine.score
    assert score is not None and score.cp == 30


def test_the_final_search_stays_visible_after_the_engine_moves() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")
    engine.reply("e7e5", SearchInfo(depth=8, score=-20, nodes=40_000, seconds=1.0, pv=[move("e7e5")]))
    status = session.snapshot().engine
    assert (status.state, status.source, status.depth, status.pv_san) == ("idle", "search", 8, ["e5"])
    assert status.score is not None and status.score.cp == 20


def test_a_book_move_has_no_score() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4 e7e5")
    status = session.snapshot().engine
    assert (status.state, status.source, status.score, status.depth) == ("idle", "book", None, None)


def test_a_line_stops_at_the_first_move_that_does_not_fit() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")
    assert engine.pending is not None
    engine.pending.on_info(SearchInfo(4, 0, 1, 0.1, [move("e7e5"), move("e7e5"), move("g1f3")]))
    assert session.snapshot().engine.pv_san == ["e5"]


def test_an_engine_failure_is_reported_and_the_move_can_be_taken_back() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")
    assert engine.pending is not None
    engine.pending.on_error(RuntimeError("secret detail"))
    state = session.snapshot()
    assert (state.engine.state, state.engine.error) == ("error", "RuntimeError")
    assert state.status == "playing" and state.actions.takeback is True
    assert session.takeback(state.game_id, 1).engine.state == "idle"


def test_an_illegal_engine_move_is_a_failure_not_a_move() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")
    engine.reply("e2e4")
    state = session.snapshot()
    assert len(state.plies) == 1
    assert (state.engine.state, state.engine.error) == ("error", "IllegalMove")


def test_untimed_games_use_the_main_py_think_time() -> None:
    session, engine, _ = make_session(think_seconds=2.0)
    play(session, engine, "e2e4")
    assert engine.pending is not None
    assert engine.pending.limits == Limits(soft_time=1.0, hard_time=2.0)


# --------------------------------------------------------------------- clocks


def test_each_clock_starts_after_that_sides_first_move() -> None:
    session, engine, time = make_session(time_control="5+3")
    assert session.snapshot().clock is not None
    time.advance(30)  # looking at a fresh board costs nothing
    play(session, engine, "e2e4")
    time.advance(30)
    clock = session.snapshot().clock
    assert clock is not None
    assert (clock.white_ms, clock.black_ms, clock.running) == (300_000, 300_000, None)
    engine.reply("e7e5")
    clock = session.snapshot().clock
    assert clock is not None and clock.running == "white"


def test_time_is_charged_and_the_increment_added() -> None:
    session, engine, time = make_session(time_control="5+3")
    play(session, engine, "e2e4 e7e5")
    time.advance(10)
    play(session, engine, "g1f3")
    clock = session.snapshot().clock
    assert clock is not None
    assert (clock.white_ms, clock.black_ms, clock.running) == (293_000, 300_000, "black")
    time.advance(4)
    engine.reply("b8c6")
    state = session.snapshot()
    assert state.clock is not None
    assert (state.clock.white_ms, state.clock.black_ms, state.clock.running) == (293_000, 299_000, "white")
    recorded = state.plies[-1].clock
    assert recorded is not None and (recorded.white_ms, recorded.black_ms) == (293_000, 299_000)


def test_the_engine_gets_its_budget_from_its_own_clock() -> None:
    session, engine, time = make_session(time_control="5+3")
    play(session, engine, "e2e4 e7e5")
    time.advance(10)
    play(session, engine, "g1f3")
    assert engine.pending is not None
    budget = timeman.allocate(300.0, 3.0)
    assert engine.pending.limits == Limits(soft_time=budget.soft, hard_time=budget.hard)


def test_the_human_loses_on_time() -> None:
    session, engine, time = make_session(time_control="3+2")
    play(session, engine, "e2e4 e7e5")
    time.advance(179)
    session.tick()
    assert session.snapshot().status == "playing"
    time.advance(2)
    session.tick()
    state = session.snapshot()
    assert state.result is not None
    assert (state.result.winner, state.result.reason) == ("black", "timeout")
    assert state.clock is not None and (state.clock.white_ms, state.clock.running) == (0, None)


def test_a_move_that_arrives_after_the_flag_fell_does_not_count() -> None:
    session, engine, time = make_session(time_control="3+2")
    play(session, engine, "e2e4 e7e5")
    game_id = session.snapshot().game_id
    time.advance(181)  # no timer ran: the move itself must notice
    with pytest.raises(Conflict) as caught:
        session.move(game_id, 2, "g1f3")
    assert caught.value.code == "game_over"
    result = session.snapshot().result
    assert result is not None and result.reason == "timeout"
    assert len(session.snapshot().plies) == 2


def test_the_engine_can_lose_on_time_and_is_stopped() -> None:
    session, engine, time = make_session(time_control="3+2")
    play(session, engine, "e2e4 e7e5 g1f3")
    thinking = engine.pending
    assert thinking is not None
    time.advance(200)
    session.tick()
    state = session.snapshot()
    assert state.result is not None
    assert (state.result.winner, state.result.reason) == ("white", "timeout")
    assert engine.pending is None  # cancelled
    thinking.reply("b8c6")
    assert len(session.snapshot().plies) == 3


def test_an_engine_answer_after_its_flag_fell_does_not_count() -> None:
    session, engine, time = make_session(time_control="3+2")
    play(session, engine, "e2e4 e7e5 g1f3")
    time.advance(200)
    engine.reply("b8c6")  # no timer ran: the answer itself must notice
    state = session.snapshot()
    assert state.result is not None and state.result.reason == "timeout"
    assert len(state.plies) == 3


def test_running_out_of_time_against_a_bare_king_is_a_draw() -> None:
    session, engine, time = make_session(time_control="3+2")
    play(session, engine, "e2e4 e7e5")
    # Reaching king-versus-king by play would take a whole game, so the position is
    # placed directly. White (the human, to move) is on the clock; Black has only a king.
    session._board.set_fen("8/8/8/8/8/5k2/4P3/4K3 w - - 0 60")
    time.advance(181)
    session.tick()
    result = session.snapshot().result
    assert result is not None
    assert (result.winner, result.reason) == (None, "timeout_insufficient_material")


def test_takeback_gives_the_time_back() -> None:
    session, engine, time = make_session(time_control="5+3")
    play(session, engine, "e2e4 e7e5")
    time.advance(20)
    play(session, engine, "g1f3")
    time.advance(5)
    engine.reply("b8c6")
    time.advance(7)
    state = session.takeback(session.snapshot().game_id, 4)
    assert state.clock is not None
    assert (state.clock.white_ms, state.clock.black_ms, state.clock.running) == (300_000, 300_000, "white")


def test_the_flag_timer_is_armed_for_the_running_clock() -> None:
    from tests.gui.fakes import FakeTime, ManualEngine
    from webgui.server.session import FLAG_TIMER_SLACK, GameSession

    delays: list[float] = []
    cancelled: list[int] = []

    def schedule(delay: float, callback: object) -> object:
        delays.append(delay)
        index = len(delays)
        return lambda: cancelled.append(index)

    time, engine = FakeTime(), ManualEngine()
    session = GameSession(engine, think_seconds=2.0, now=time.now, schedule=schedule)  # type: ignore[arg-type]
    session.new_game("white", "3+2")
    assert delays == []  # nothing is running before both sides have moved
    play(session, engine, "e2e4 e7e5")
    assert delays[-1] == pytest.approx(180 + FLAG_TIMER_SLACK)
    session.resign(session.snapshot().game_id)
    assert cancelled[-1] == len(delays)  # the last timer was cancelled and none replaced it


# ------------------------------------------------------------- PGN, listeners


def test_pgn_carries_the_moves_and_the_result() -> None:
    session, engine, _ = make_session(time_control="5+3")
    play(session, engine, "e2e4 e7e5 g1f3")
    pgn = session.pgn()
    assert '[White "Human"]' in pgn and '[Black "chessgm"]' in pgn
    assert '[Date "2026.11.13"]' in pgn and '[TimeControl "300+3"]' in pgn
    assert '[Result "*"]' in pgn
    assert pgn.rstrip().endswith("1. e4 e5 2. Nf3 *")
    state = session.resign(session.snapshot().game_id)
    assert '[Result "0-1"]' in state.pgn and state.pgn.rstrip().endswith("0-1")


def test_pgn_names_follow_the_colours_and_time_forfeits_are_marked() -> None:
    session, engine, time = make_session(human="black", time_control="3+2")
    play(session, engine, "e2e4 e7e5 g1f3")
    time.advance(500)
    session.tick()
    pgn = session.pgn()
    assert '[White "chessgm"]' in pgn and '[Black "Human"]' in pgn
    assert '[Termination "time forfeit"]' in pgn and '[Result "1-0"]' in pgn


def test_listeners_hear_about_changes_until_they_unsubscribe() -> None:
    session, engine, _ = make_session()
    calls: list[int] = []
    unsubscribe = session.subscribe(lambda: calls.append(1))
    play(session, engine, "e2e4")
    heard = len(calls)
    assert heard >= 1
    unsubscribe()
    engine.reply("e7e5")
    assert len(calls) == heard


def test_close_shuts_the_engine_and_ignores_late_answers() -> None:
    session, engine, _ = make_session()
    play(session, engine, "e2e4")
    thinking = engine.pending
    assert thinking is not None
    session.close()
    assert engine.closed is True
    thinking.reply("e7e5")
    assert len(session.snapshot().plies) == 1
