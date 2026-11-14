// A thin bar beside the board: how much of it is white is how the engine sees the game.

import type { CSSProperties } from "react";
import type { Colour, Score } from "../api/types";
import { formatScore, whiteShare } from "../format";

interface Props {
  score: Score | null;
  orientation: Colour;
}

export function EvalBar({ score, orientation }: Props) {
  const share = { "--white-share": whiteShare(score) } as CSSProperties;
  const label = score === null ? "No evaluation yet" : `Evaluation ${formatScore(score)}, from White's side`;
  return (
    <div
      className="eval-bar"
      data-orientation={orientation}
      data-empty={score === null}
      role="img"
      aria-label={label}
      style={share}
    >
      <div className="eval-bar__white" />
    </div>
  );
}
