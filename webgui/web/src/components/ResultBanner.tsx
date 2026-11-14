// How the game ended, said once and plainly, with the obvious next step.

import type { Colour, GameResult } from "../api/types";
import { outcomeFor, resultHeadline } from "../format";

interface Props {
  result: GameResult;
  human: Colour;
  busy: boolean;
  onRematch: () => void;
  onNewGame: () => void;
}

export function ResultBanner({ result, human, busy, onRematch, onNewGame }: Props) {
  const { title, detail } = resultHeadline(result, human);
  return (
    <section className="result" data-outcome={outcomeFor(result, human)} data-testid="result">
      <div>
        <h2 className="result__title">{title}</h2>
        <p className="result__detail">{detail}</p>
      </div>
      <div className="result__actions">
        <button type="button" className="button button--primary" onClick={onRematch} disabled={busy}>
          Rematch
        </button>
        <button type="button" className="button" onClick={onNewGame}>
          Change settings
        </button>
      </div>
    </section>
  );
}
