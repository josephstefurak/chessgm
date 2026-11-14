// Asks which piece a pawn becomes, drawn over the square it is promoting on.

import { createElement, useEffect, useRef, type CSSProperties } from "react";
import type { Colour, PromotionPiece } from "../api/types";

const CHOICES: { piece: PromotionPiece; role: string; name: string }[] = [
  { piece: "q", role: "queen", name: "Queen" },
  { piece: "n", role: "knight", name: "Knight" },
  { piece: "r", role: "rook", name: "Rook" },
  { piece: "b", role: "bishop", name: "Bishop" },
];

interface Props {
  square: string;
  colour: Colour;
  orientation: Colour;
  onChoose: (piece: PromotionPiece) => void;
  onCancel: () => void;
}

export function PromotionPicker({ square, colour, orientation, onChoose, onCancel }: Props) {
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    first.current?.focus();
  }, []);

  const file = square.charCodeAt(0) - "a".charCodeAt(0);
  const column = orientation === "white" ? file : 7 - file;
  // The pawn promotes on the far rank, which is the top of the board unless it is flipped.
  const anchor = orientation === colour ? "top" : "bottom";
  const position = { "--promotion-column": column } as CSSProperties;

  return (
    <div
      className="promotion cg-wrap"
      data-anchor={anchor}
      role="dialog"
      aria-label="Choose a piece to promote to"
      onClick={onCancel}
      onKeyDown={(event) => {
        if (event.key === "Escape") onCancel();
      }}
    >
      <div className="promotion__choices" style={position}>
        {CHOICES.map(({ piece, role, name }, index) => (
          <button
            key={piece}
            ref={index === 0 ? first : null}
            type="button"
            className="promotion__choice"
            aria-label={name}
            data-piece={piece}
            onClick={(event) => {
              event.stopPropagation();
              onChoose(piece);
            }}
          >
            {createElement("piece", { className: `${role} ${colour}` })}
          </button>
        ))}
      </div>
    </div>
  );
}
