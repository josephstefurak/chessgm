# chessgm

A chess engine written in Python on top of [`python-chess`](https://python-chess.readthedocs.io/). Play it in the browser or the terminal, or run it as a Lichess bot through [`lichess-bot`](https://github.com/lichess-bot-devs/lichess-bot).

## Setup

```bash
conda activate lichessbot          # Python 3.11
pip install -r requirements.txt    # just python-chess
```

## Play in the browser

A board you can drag pieces on, with clocks, a move list, the engine's evaluation and its expected line.

One-time setup (needs Node 22 or newer):

```bash
pip install -r requirements-gui.txt   # the local web server
cd webgui/web
npm install
npm run build
```

Then, from the project folder:

```bash
python gui.py
```

It opens `http://127.0.0.1:8765` in your browser. Stop it with Ctrl-C. Rebuild (`npm run build`) after changing anything in `webgui/web`.

| Option | Meaning |
|---|---|
| `--port 9000` | Use another local port (default 8765) |
| `--time 2` | Most seconds the engine may think per move in an untimed game (default 2) |
| `--no-browser` | Do not open a browser tab |

What you can do:

- **Move** by dragging a piece or clicking it and then its destination. Legal squares are marked. A pawn reaching the last rank asks which piece you want.
- **New game** lets you choose your colour (White, Black or Random) and the time control: Untimed, 3+2, 5+3, 10+0 or 15+10. In a timed game each clock starts after that side's first move, and running out of time loses.
- **Take back** undoes your last move (and the engine's reply). **Resign** asks you to confirm.
- **Review** the game with the left and right arrow keys, Home and End, or by clicking a move. The board is read-only while you look back. `F` flips the board.
- **Engine** shows the evaluation (from White's side), search depth and the line the engine expects. Hide it with the chart button at the top right if you would rather not see it; the choice is remembered.
- **Copy PGN**, **Download PGN** and **Copy FEN** take the game elsewhere.
- The speaker button mutes the sounds.

The page is served to this machine only: the server listens on 127.0.0.1 and refuses requests from any other site. Nothing is saved between runs.

## Play in the terminal

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

The browser GUI has its own checks, run from `webgui/web`:

```bash
npm run typecheck    # TypeScript
npm run lint         # ESLint
npm test             # unit tests
npm run build        # production build
npm run e2e          # browser tests against that build (starts the Python server itself)
```

While working on the interface, `python gui.py --no-browser` in one terminal and `npm run dev` in another gives live reload at `http://127.0.0.1:5173`.

See `CLAUDE.md` for the layout and rules of the codebase and `DECISIONS.md` for why things are the way they are.

## Licence of the browser GUI

`webgui/` is offered under the GNU General Public License, version 3 or later (`webgui/LICENSE`), because its board is [chessground](https://github.com/lichess-org/chessground), which is GPL-3.0-or-later and whose bundled piece set (cburnett) is used as shipped. The interface also uses the Newsreader, Geist and Geist Mono typefaces (SIL Open Font License) and Phosphor icons (MIT), all installed through `npm` and served locally.

## Legacy code

`bot.py`, `evaluator.py`, `features.py`, `neural_net.py`, `train.py`, `train_neural.py` and `legacy_uci.py` are the original engine and its training scripts. They are kept for reference and as a baseline opponent, and are not used for play. They need `requirements-train.txt`.
