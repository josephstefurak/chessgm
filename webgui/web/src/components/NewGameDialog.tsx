// Colour and time control for the next game.

import { useEffect, useRef, useState } from "react";
import type { ColourChoice, TimeControl } from "../api/types";
import { timeControlHint, timeControlLabel } from "../format";

const COLOURS: { value: ColourChoice; label: string }[] = [
  { value: "white", label: "White" },
  { value: "black", label: "Black" },
  { value: "random", label: "Random" },
];

interface Props {
  open: boolean;
  timeControls: TimeControl[];
  initial: { human: ColourChoice; timeControl: string | null };
  /** True when starting now would abandon a game in progress. */
  gameInProgress: boolean;
  onStart: (human: ColourChoice, timeControl: string | null) => void;
  onClose: () => void;
}

export function NewGameDialog({ open, timeControls, initial, gameInProgress, onStart, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [human, setHuman] = useState<ColourChoice>(initial.human);
  const known = timeControls.some((control) => control.id === initial.timeControl);
  const [timeControl, setTimeControl] = useState<string | null>(known ? initial.timeControl : null);

  useEffect(() => {
    const element = dialog.current;
    if (element === null) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  const chosen = timeControls.find((control) => control.id === timeControl);

  return (
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby="new-game-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose(); // a click on the backdrop
      }}
    >
      <form
        className="dialog__form"
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          onStart(human, timeControl);
        }}
      >
        <h2 id="new-game-title" className="dialog__title">
          New game
        </h2>

        <fieldset className="field">
          <legend className="field__label">Play as</legend>
          <div className="choices" data-columns="3">
            {COLOURS.map((option) => (
              <label key={option.value} className="choice">
                <input
                  type="radio"
                  name="human"
                  value={option.value}
                  checked={human === option.value}
                  onChange={() => setHuman(option.value)}
                />
                <span className="choice__face">
                  <span className="choice__swatch" data-colour={option.value} aria-hidden="true" />
                  {option.label}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="field">
          <legend className="field__label">Time</legend>
          <div className="choices" data-columns="5">
            <label className="choice">
              <input
                type="radio"
                name="time"
                value=""
                checked={timeControl === null}
                onChange={() => setTimeControl(null)}
              />
              <span className="choice__face">Untimed</span>
            </label>
            {timeControls.map((control) => (
              <label key={control.id} className="choice">
                <input
                  type="radio"
                  name="time"
                  value={control.id}
                  checked={timeControl === control.id}
                  onChange={() => setTimeControl(control.id)}
                />
                <span className="choice__face choice__face--number">{timeControlLabel(control)}</span>
              </label>
            ))}
          </div>
          <p className="field__hint">
            {chosen ? timeControlHint(chosen) : "No clocks. The engine takes a second or two per move."}
          </p>
        </fieldset>

        {gameInProgress && <p className="dialog__warning">Starting a new game ends the one in progress.</p>}

        <div className="dialog__actions">
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="button button--primary">
            Start game
          </button>
        </div>
      </form>
    </dialog>
  );
}
