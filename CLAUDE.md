# chessgm

A Python chess engine on top of `python-chess`, playable locally (browser or terminal) and on Lichess (bot account `joeystef7`) through `lichess-bot`.

## Layout

| Path | Role |
|---|---|
| `engine/weights.py` | Every eval number. Tuning touches only this file |
| `engine/evaluation.py` | Static eval from bitboards. Returns White-relative centipawns |
| `engine/search.py` | `Searcher`: iterative-deepening negamax. Never prints |
| `engine/timeman.py` | Clock and increment to a soft and hard time limit |
| `uci.py` | UCI front end. This is what `lichess-bot` launches |
| `main.py` | Local play in the terminal |
| `gui.py` | Local play in the browser: launcher for the server in `webgui/server` |
| `webgui/server/` | Local HTTP server that owns the game: `session.py` (all rules and state), `clock.py`, `engine_port.py` (the engine on a worker thread), `schemas.py` (wire format), `security.py`, `events.py`, `app.py` (routes) |
| `webgui/web/` | The browser UI: React + TypeScript, built with Vite. `src/theme/tokens.css` holds every visual value; `src/board/Board.tsx` is the only file that touches chessground |
| `opening_book.py` | Hardcoded opening lines (unchanged from the original engine) |
| `tools/match.py` | Engine-vs-engine match runner for any two UCI engines |
| `tools/bench.py` | Speed benchmark on ten fixed positions |
| `tools/openings.txt` | 60 balanced six-ply openings used by matches (made by `tools/make_openings.py`) |
| `match.py` | Shortcut: match against Stockfish at a fixed rating |
| `tests/` | pytest suite. `tests/positions.py` holds positions verified with Stockfish |
| `tests/gui/` | Server tests for the GUI, plus `fakes.py` (manual and scripted engines) and `e2e_server.py` (the server the browser tests run against) |
| `bot.py`, `evaluator.py`, `features.py`, `neural_net.py`, `train.py`, `train_neural.py`, `legacy_uci.py` | **Legacy, frozen.** The original minimax engine, its UCI wrapper and training scripts. Not used for play |

## How the engine works

**Search** (`engine/search.py`)
- Negamax: every score is from the side to move. Mate is `MATE - ply`, so faster mates score higher. Draws (repetition, 50-move rule, insufficient material, stalemate) score 0.
- Iterative deepening with an aspiration window. Depth 1 always completes, so the move returned has always been searched.
- Transposition table: a dict keyed by `position_key(board)`, storing depth, bound, score and best move. It persists across moves in a game and is cleared on `ucinewgame`.
- Move ordering: hash move, captures by most valuable victim / least valuable attacker, queen promotions, two killer moves per ply, history.
- Pruning and reductions, each switchable in `SearchConfig` and as a UCI option: null move, late move reductions, reverse futility, futility, late move pruning, check extension, bad-capture pruning in quiescence.
- Quiescence: captures and queen promotions only, delta pruning, at most 10 plies, full evasions when in check.
- The clock and the stop flag are checked every 256 nodes in both search and quiescence.

**Evaluation** (`engine/evaluation.py`)
- Tapered: each term has a middlegame and an endgame value, blended by remaining material. The pair is packed into one int (`(eg << 16) + mg`).
- Terms: material and piece-square tables (PeSTO), passed/doubled/isolated pawns (cached by pawn structure), rooks on open files, bishop pair, king pawn shelter (cached), tempo.
- Endgame knowledge when little material is left: unstoppable passed pawn, opposition in pawn endings, driving a bare king to the edge, and scaling down pawnless positions that cannot normally be won.

**Time** (`engine/timeman.py`): plan `clock / 40 + 0.8 * increment` per move; stop starting new depths at 55% of that; hard stop at 2.5x, never more than half the clock.

## How the browser GUI works

- **The server owns the game; the browser holds no chess rules.** The browser posts intents (`/api/game`, `/api/move`, `/api/takeback`, `/api/resign`) and receives a full snapshot: legal destinations, which moves are promotions, SAN, a FEN per ply, clocks, result, engine info, PGN. It also follows `/api/events` (server-sent events, always the latest snapshot, never a backlog). Every request carries `game_id` and `ply`; a stale one gets a 409.
- **Engine**: `engine_port.SearchEngine` runs the `Searcher` on one long-lived worker thread, book first, as `main.py` does. Requests are numbered and re-checked at every completed depth, because `Searcher.search` clears its stop flag on entry and a stop sent just before it starts would be lost. Untimed games use `main.DEFAULT_THINK_SECONDS`; timed games use `engine.timeman.allocate` on the engine's clock.
- **Scores** are converted from side-to-move to White's point of view in `session._score_out` and nowhere else.
- **Clocks**: the server is the authority and the browser only animates between snapshots. Flag fall is checked under the session lock by whichever arrives first, a request or the flag timer. Each side's clock starts after its own first move.
- **Game end** is `session._ending`: draws by repetition and the 50-move rule are automatic only once they have happened. This differs from `main.py`'s `outcome(claim_draw=True)` on purpose (see `DECISIONS.md`).
- **Local only**: the server binds to 127.0.0.1; `security.LocalOnlyMiddleware` refuses any other Host, and any POST without this server's exact Origin, a JSON content type and a body under 1 KB. Responses carry a strict CSP (no inline script or style). `tests/gui/test_http.py` enumerates every route and fails until each is classified.
- **Wire format**: `webgui/server/schemas.py` and `webgui/web/src/api/types.ts` mirror each other by hand. Change both together.

## Rules for this codebase

- **Scores are from the side to move** in `engine/search.py`. `engine/evaluation.py` is White-relative and the search flips it. The legacy code used Black-relative scores and got signs wrong; do not mix conventions. `tests/test_evaluation.py::test_colour_symmetry` guards this.
- **Front ends hold no engine logic.** `uci.py`, `main.py` and the GUI (`gui.py`, `webgui/`) parse input, call `engine`, format output. `engine/` never prints and never imports from the front ends or from legacy modules.
- **Only UCI goes to stdout in `uci.py`.** Diagnostics use `info string`.
- **All eval numbers live in `engine/weights.py`.**
- **Strength changes are measured, not assumed.** Check speed with `tools/bench.py` and strength with an A/B match in `tools/match.py` before keeping a search or eval change. The rule and every result are in `DECISIONS.md`. If the match summary prints a forfeit warning, the result is not a strength measurement.
- **External input** is the UCI stream, the terminal prompt and the GUI's HTTP requests. All are validated at the boundary: a bad command must never crash the engine. HTTP bodies are strict pydantic models in `webgui/server/schemas.py`.
- **The browser UI is presentation only.** No chess rules in `webgui/web` (ESLint forbids importing a rules library or the server's code), and no colours, fonts or sizes outside `src/theme/tokens.css`.
- **Browser tests are a gate** for any change to the GUI's markup, copy or accessible names. They run against the production build (`npm run build`, then `npm run e2e`).
- **Test positions are verified with Stockfish** before they go into `tests/positions.py`. Hand-written positions are often illegal or not what they claim.
- `chess` is pinned because the code reads `Board` bitboard attributes directly.

## Environment

- Python: `/opt/anaconda3/envs/lichessbot/bin/python` (3.11). The default `python` is conda base and is the wrong env.
- Terminal and Lichess play need only `requirements.txt`. The browser GUI adds `requirements-gui.txt` (fastapi, uvicorn, pinned) and Node 22 for `webgui/web`. Training needs `requirements-train.txt`. Dev tools are in `requirements-dev.txt`.
- Playwright is pinned to the release whose Chromium build is already cached on this machine; bumping it downloads a new browser.
- Stockfish: `/Users/josephstefurak/stockfish/stockfish-macos-m1-apple-silicon` (minimum `UCI_Elo` is 1320). Override with `CHESSGM_STOCKFISH`.
- `lichess-bot` lives in `/Users/josephstefurak/lichess-bot/` and launches `uci.py` from this folder. Its `config.yml` holds the API token; never read, print or commit it.

## Commands

```bash
PY=/opt/anaconda3/envs/lichessbot/bin/python
$PY -m pytest                       # tests (about 25s)
$PY -m ruff check .                 # lint
$PY -m mypy                         # typecheck (configured in pyproject.toml)
$PY tools/bench.py                  # depth and nodes/s at 1s per position
$PY tools/bench.py --depth 6        # deterministic node counts
$PY match.py --elo 1700 --games 40  # match vs Stockfish
$PY main.py                         # play in the terminal
$PY gui.py                          # play in the browser (build the UI first)

cd webgui/web                       # the browser UI
npm run build                       # typecheck, then production build into dist/
npm run lint && npm test            # ESLint, unit tests
npm run e2e                         # browser tests against dist/ (starts the Python servers itself)
```

Matches take minutes and use several cores. Do not run two at once, and do not edit engine files while a match is running from this folder (each game starts `uci.py` fresh); copy the folder or use a git worktree for the side that must stay fixed.

## Measurements

All measured on 2026-11-13 on the M1 Max. Update this table whenever a strength-affecting change lands. "Legacy" is the original engine (`legacy_uci.py`).

| Measure | Legacy | Current |
|---|---|---|
| Nodes per second, middlegame | about 5,500 | 32,000 to 36,000 |
| Depth completed in 1s, six opening/middlegame positions (`tools/bench.py`) | 2 (none at all in the capture-heavy one) | 6 to 8 |
| One static eval | 105 to 233 microseconds | about 12 microseconds |
| Engine startup | 1.4s | 0.13s |
| vs Stockfish `UCI_Elo` 1320, 1s/move, 40 games | 42.5% | not run (see stronger opponents below) |
| vs Stockfish `UCI_Elo` 1700, 0.5s/move, 40 games | not run | 82.5% (95% CI 71.8% to 93.2%) |
| vs Stockfish `UCI_Elo` 2000, 1s/move, 40 games | not run | 80.0% (95% CI 69.2% to 90.8%) |
| Current vs legacy, 1s/move, 24 games | | 24 wins, 0 draws, 0 losses |
| Self-play on a 60+1 clock, 8 games | | no time losses; 1.6s average move, 5.6s slowest, average depth 8.9 |

Stockfish played at 0.1s/move in all of these. Its limited-strength ratings are not Lichess ratings; use them to compare versions, not to predict a Lichess number. Forty games gives a confidence interval of roughly plus or minus 10 points.

The individual A/B results for each search technique and eval change are in `DECISIONS.md`.

## Open Questions

- **Is a 2 second cap the right feel for local play?** Matters because it sets the strength/wait trade-off in `main.py`. The code runs on a 2s cap (`--time` overrides it), stopping new depths at 1s. Safe to keep building: it is one constant and a flag.
- **Are premoves wanted in the browser GUI?** Matters because a premove has to be held in the browser and sent when the engine's reply arrives, which is the first piece of game timing the browser would own. The code runs with premoves off. Safe to keep building: chessground supports them and the board sits behind one component (`webgui/web/src/board/Board.tsx`).
- **Should the engine panel be visible by default?** Matters only for first impressions; it is one default in `webgui/web/src/state/prefs.ts`. The code shows it by default and remembers if it is hidden.
- **Are 3+2, 5+3, 10+0 and 15+10 the right time controls, and is a custom one wanted?** Matters because a custom control needs input validation and a new field in the new-game request. The code offers the four presets from `webgui/server/clock.py`. Safe to keep building: presets are one tuple.
- **Should the neural net and the training scripts be kept at all?** They are frozen and unused. If learning is resumed, the recommended route is fitting `engine/weights.py` by regression on Stockfish-labelled positions, not the old net. Nothing depends on the answer today.
