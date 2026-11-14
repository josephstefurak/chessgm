# chessgm

A Python chess engine on top of `python-chess`, playable locally and on Lichess (bot account `joeystef7`) through `lichess-bot`.

## Layout

| Path | Role |
|---|---|
| `engine/` | The playing engine. `weights.py` (all eval numbers), `evaluation.py` (bitboard eval), `search.py` (negamax search), `timeman.py` (clock to time budget) |
| `uci.py` | UCI front end. This is what `lichess-bot` launches |
| `main.py` | Local play in the terminal |
| `opening_book.py` | Hardcoded opening lines |
| `tools/bench.py` | Speed benchmark: depth and nodes/s on a fixed position set |
| `tools/match.py` | Engine-vs-engine match runner (any two UCI engines, including Stockfish) |
| `match.py` | Shortcut for a match against Stockfish |
| `tests/` | pytest suite |
| `bot.py`, `evaluator.py`, `features.py`, `neural_net.py`, `train.py`, `train_neural.py` | **Legacy, frozen.** Old minimax engine and training scripts. Not used for play. Do not import these from `engine/`, `uci.py` or `main.py` |

## Rules for this codebase

- **Scores are from the side to move** everywhere in `engine/search.py` (negamax). `engine/evaluation.py` returns a White-relative score and the search flips it. The legacy code used Black-relative scores; do not mix the two.
- **Front ends do not contain engine logic.** `uci.py` and `main.py` parse input, call `engine`, and format output. `engine/` never prints.
- **Only UCI goes to stdout in `uci.py`.** Diagnostics use `info string`.
- **All eval numbers live in `engine/weights.py`**, so tuning never touches logic.
- **Strength changes are measured, not assumed.** Run `tools/bench.py` and an A/B match with `tools/match.py` before keeping a search or eval change. See `DECISIONS.md` for the rule.
- External input is the UCI stream and the CLI prompt. Both are validated at the boundary; a bad command must never crash the engine.

## Environment

- Python: `/opt/anaconda3/envs/lichessbot/bin/python` (3.11). The default `python` is conda base and is the wrong env.
- Play needs only `requirements.txt`. Training needs `requirements-train.txt`. Dev tools are in `requirements-dev.txt`.
- Stockfish: `/Users/josephstefurak/stockfish/stockfish-macos-m1-apple-silicon` (minimum `UCI_Elo` is 1320).
- `lichess-bot` lives in `/Users/josephstefurak/lichess-bot/` and launches `uci.py` from this folder. Its `config.yml` holds the API token; never print or commit it.

## Commands

```bash
PY=/opt/anaconda3/envs/lichessbot/bin/python
$PY -m pytest                      # tests
$PY -m ruff check .                # lint
$PY -m mypy                        # typecheck (configured in pyproject.toml)
$PY tools/bench.py                 # speed benchmark
$PY match.py --elo 1320 --games 40 # match vs Stockfish
$PY main.py                        # play locally
```

## Open Questions

None yet.
