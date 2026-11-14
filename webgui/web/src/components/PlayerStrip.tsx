// The line above and below the board: who is sitting there, what they are
// doing, and their clock.

import type { Colour } from "../api/types";
import { Clock } from "./Clock";

interface Props {
  name: string;
  colour: Colour;
  status: string;
  tone: "quiet" | "active" | "bad";
  clockMs: number | null;
  clockRunning: boolean;
  clockLabel: string;
  clockTestId: string;
  onLowTime?: (() => void) | undefined;
}

export function PlayerStrip(props: Props) {
  const { name, colour, status, tone, clockMs, clockRunning, clockLabel, clockTestId, onLowTime } = props;
  return (
    <div className="strip">
      <span className="strip__swatch" data-colour={colour} aria-hidden="true" />
      <span className="strip__name">{name}</span>
      <span className="strip__status" data-tone={tone}>
        {tone === "active" && <span className="strip__pulse" aria-hidden="true" />}
        {status}
      </span>
      {clockMs !== null && (
        <Clock
          ms={clockMs}
          running={clockRunning}
          label={clockLabel}
          testId={clockTestId}
          onLowTime={onLowTime}
        />
      )}
    </div>
  );
}
