// The score sheet. Any move can be clicked to look at that position.

import { CaretDoubleLeft, CaretDoubleRight, CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import type { Ply } from "../api/types";
import type { Step } from "../state/reducer";
import { IconButton } from "./IconButton";

interface Props {
  plies: Ply[];
  /** The ply on the board right now (0 is the starting position). */
  shownPly: number;
  live: boolean;
  emptyText: string;
  onGoto: (ply: number) => void;
  onStep: (step: Step) => void;
}

export function MoveList({ plies, shownPly, live, emptyText, onGoto, onStep }: Props) {
  const current = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest" });
  }, [shownPly, plies.length]);

  const rows: { number: number; white: Ply | undefined; black: Ply | undefined }[] = [];
  for (let index = 0; index < plies.length; index += 2) {
    rows.push({ number: index / 2 + 1, white: plies[index], black: plies[index + 1] });
  }

  const cell = (ply: Ply | undefined) =>
    ply === undefined ? (
      <span className="moves__cell" />
    ) : (
      <button
        type="button"
        ref={ply.ply === shownPly ? current : null}
        className="moves__cell moves__move"
        aria-current={ply.ply === shownPly ? "step" : undefined}
        onClick={() => onGoto(ply.ply)}
      >
        {ply.san}
      </button>
    );

  return (
    <section className="panel moves" aria-label="Moves">
      <header className="panel__header">
        <h2 className="panel__title">Moves</h2>
        <div className="moves__nav">
          <IconButton label="First move" onClick={() => onStep("first")} disabled={shownPly === 0}>
            <CaretDoubleLeft weight="bold" />
          </IconButton>
          <IconButton label="Previous move" onClick={() => onStep("previous")} disabled={shownPly === 0}>
            <CaretLeft weight="bold" />
          </IconButton>
          <IconButton label="Next move" onClick={() => onStep("next")} disabled={live}>
            <CaretRight weight="bold" />
          </IconButton>
          <IconButton label="Last move" onClick={() => onStep("last")} disabled={live}>
            <CaretDoubleRight weight="bold" />
          </IconButton>
        </div>
      </header>

      {rows.length === 0 ? (
        <p className="moves__empty">{emptyText}</p>
      ) : (
        <ol className="moves__rows" data-testid="moves">
          {rows.map((row) => (
            <li key={row.number} className="moves__row">
              <span className="moves__number">{row.number}.</span>
              {cell(row.white)}
              {cell(row.black)}
            </li>
          ))}
        </ol>
      )}

      {!live && (
        <div className="moves__review">
          <span>
            Looking at move {shownPly} of {plies.length}
          </span>
          <button type="button" className="link-button" onClick={() => onStep("last")}>
            Back to the game
          </button>
        </div>
      )}
    </section>
  );
}
