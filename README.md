# chessgm

A chess engine written in Python on top of [`python-chess`](https://python-chess.readthedocs.io/). Play it in the terminal, or run it as a Lichess bot through [`lichess-bot`](https://github.com/lichess-bot-devs/lichess-bot).

## Setup

```bash
conda activate lichessbot          # Python 3.11
pip install -r requirements.txt    # just python-chess
```

## Play against it

```bash
python main.py
```

Pick a colour, then type moves as `Nf3` or `g1f3`. Other commands: `undo`, `help`, `quit`.

| Option | Meaning |
|---|---|
| `--time 2` | Most seconds the engine may think per move (default 2) |
| `--color w` or `b` | Skip the colour question |
| `--fen "..."` | Start from a position |

## Run it on Lichess

`lichess-bot` launches `uci.py` from this folder, so there is nothing to deploy. After changing the engine, restart `lichess-bot`:

```bash
cd /Users/josephstefurak/lichess-bot
python lichess-bot.py
```

The engine declares these UCI options, which can be set under `uci_options` in `lichess-bot`'s `config.yml` if wanted: `Move Overhead` (ms, default 30), `Hash` (MB, default 128), `OwnBook` (default true). None of them need to be set.

## Measure it

```bash
python match.py --elo 1700 --games 40    # match against Stockfish at a fixed rating
python tools/bench.py                    # depth and nodes/s on ten fixed positions
python tools/bench.py --depth 6          # deterministic node counts, for checking refactors
```

Any two UCI engines can be matched with `tools/match.py`, for example the current engine against the old one:

```bash
python tools/match.py --a "python uci.py" --b "python legacy_uci.py" --games 40 --movetime 0.5
```

## Develop

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m mypy
```

See `CLAUDE.md` for the layout and rules of the codebase and `DECISIONS.md` for why things are the way they are.

## Legacy code

`bot.py`, `evaluator.py`, `features.py`, `neural_net.py`, `train.py`, `train_neural.py` and `legacy_uci.py` are the original engine and its training scripts. They are kept for reference and as a baseline opponent, and are not used for play. They need `requirements-train.txt`.
