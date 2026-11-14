"""Everything that crosses the HTTP boundary, in both directions.

Requests are strict: wrong types, unknown fields and out-of-range values are
rejected before any game code runs. The snapshot is the whole state of the game
as the browser needs it; the browser derives nothing about chess for itself.

`webgui/web/src/api/types.ts` mirrors these models by hand. Change both together.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Colour = Literal["white", "black"]
ColourChoice = Literal["white", "black", "random"]
Reason = Literal[
    "checkmate",
    "stalemate",
    "insufficient_material",
    "threefold_repetition",
    "fifty_moves",
    "fivefold_repetition",
    "seventyfive_moves",
    "resignation",
    "timeout",
    "timeout_insufficient_material",
]

GameId = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
PlyCount = Annotated[int, Field(ge=0, le=20_000)]
UciMove = Annotated[str, Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")]
TimeControlId = Annotated[str, Field(pattern=r"^[0-9]{1,3}\+[0-9]{1,3}$")]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class NewGameRequest(_Request):
    human: ColourChoice
    time_control: TimeControlId | None


class MoveRequest(_Request):
    game_id: GameId
    ply: PlyCount
    uci: UciMove


class TakebackRequest(_Request):
    game_id: GameId
    ply: PlyCount


class ResignRequest(_Request):
    game_id: GameId


# ------------------------------------------------------------------ snapshot


class TimeControlOut(BaseModel):
    id: str
    initial_ms: int
    increment_ms: int


class ClockPair(BaseModel):
    white_ms: int
    black_ms: int


class ClockOut(ClockPair):
    running: Colour | None


class PlyOut(BaseModel):
    ply: int  # 1 for White's first move
    san: str
    uci: str
    fen: str  # the position after this move
    check: Colour | None  # the side in check after this move
    capture: bool
    clock: ClockPair | None  # both clocks after this move


class LegalOut(BaseModel):
    dests: dict[str, list[str]]  # from-square -> to-squares, for the human only
    promotions: list[str]  # "e7e8"-style from+to pairs that need a piece choice


class ScoreOut(BaseModel):
    """From White's point of view. Exactly one field is set."""

    cp: int | None = None
    mate: int | None = None  # positive: White mates in this many moves


class EngineOut(BaseModel):
    state: Literal["idle", "thinking", "error"]
    source: Literal["book", "search"] | None
    ply: int | None  # number of moves played when the engine looked at the position
    depth: int | None
    score: ScoreOut | None
    pv_san: list[str]
    nodes: int | None
    ms: int | None
    error: str | None


class ResultOut(BaseModel):
    winner: Colour | None
    reason: Reason


class ActionsOut(BaseModel):
    takeback: bool
    resign: bool


class Snapshot(BaseModel):
    game_id: str
    version: int
    human: Colour
    status: Literal["playing", "finished"]
    result: ResultOut | None
    turn: Colour
    start_fen: str
    plies: list[PlyOut]
    legal: LegalOut
    actions: ActionsOut
    time_control: str | None
    time_controls: list[TimeControlOut]
    clock: ClockOut | None
    engine: EngineOut
    pgn: str
