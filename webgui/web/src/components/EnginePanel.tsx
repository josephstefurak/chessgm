// What the engine made of the position the last time it looked.

import type { EngineStatus } from "../api/types";
import { formatLine, formatNodes, formatScore } from "../format";

interface Props {
  engine: EngineStatus;
  onHide: () => void;
}

export function EnginePanel({ engine, onHide }: Props) {
  const facts: string[] = [];
  if (engine.depth !== null) facts.push(`Depth ${engine.depth}`);
  if (engine.nodes !== null) facts.push(`${formatNodes(engine.nodes)} nodes`);
  if (engine.ms !== null) facts.push(`${(engine.ms / 1000).toFixed(1)} s`);

  let body;
  if (engine.state === "error") {
    body = (
      <p className="engine__note" data-tone="bad" role="alert">
        The engine stopped with an error ({engine.error ?? "unknown"}). Take your move back or start a new game.
      </p>
    );
  } else if (engine.source === "book") {
    body = (
      <>
        <p className="engine__score engine__score--word" data-testid="engine-score">
          Opening book
        </p>
        <p className="engine__note">Played from the opening book, so there is no search to show.</p>
      </>
    );
  } else if (engine.depth !== null && engine.score !== null) {
    body = (
      <>
        <p className="engine__score" data-testid="engine-score">
          {formatScore(engine.score)}
          <span className="engine__score-note">+ favours White</span>
        </p>
        <p className="engine__facts" data-testid="engine-facts">
          {facts.join(" · ")}
        </p>
        {engine.pv_san.length > 0 && (
          <p className="engine__line" data-testid="engine-line">
            {formatLine(engine.ply ?? 0, engine.pv_san)}
          </p>
        )}
      </>
    );
  } else if (engine.state === "thinking") {
    body = <p className="engine__note">Thinking…</p>;
  } else {
    body = <p className="engine__note">The engine's view of the game appears here after its first search.</p>;
  }

  return (
    <section className="panel engine" aria-label="Engine" data-state={engine.state}>
      <header className="panel__header">
        <h2 className="panel__title">Engine</h2>
        <button type="button" className="link-button" onClick={onHide}>
          Hide
        </button>
      </header>
      <div className="engine__body" aria-live="off">
        {body}
      </div>
    </section>
  );
}
