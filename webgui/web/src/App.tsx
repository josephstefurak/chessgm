// The page: lays the pieces of the interface out around the board and connects
// them to the game. It decides what to show, never what is legal.

import { ChartLine, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import type { ColourChoice, PromotionPiece, Snapshot } from "./api/types";
import { playSound, unlockSound } from "./audio/sounds";
import { Board } from "./board/Board";
import { PromotionPicker } from "./board/PromotionPicker";
import { Actions } from "./components/Actions";
import { EnginePanel } from "./components/EnginePanel";
import { EvalBar } from "./components/EvalBar";
import { IconButton } from "./components/IconButton";
import { MoveList } from "./components/MoveList";
import { NewGameDialog } from "./components/NewGameDialog";
import { PlayerStrip } from "./components/PlayerStrip";
import { ResultBanner } from "./components/ResultBanner";
import { colourName, errorText, resultHeadline, timeControlLabel } from "./format";
import { usePrefs } from "./state/prefs";
import { orientationOf, positionOf } from "./state/reducer";
import { useGame } from "./state/useGame";

const ENGINE_NAME = "chessgm";

interface PendingPromotion {
  positionKey: string;
  from: string;
  to: string;
}

function announcement(snapshot: Snapshot): string {
  if (snapshot.result !== null) {
    const { title, detail } = resultHeadline(snapshot.result, snapshot.human);
    return `${title} ${detail}.`;
  }
  const last = snapshot.plies[snapshot.plies.length - 1];
  if (last === undefined) return "";
  const mover = last.ply % 2 === 1 ? "White" : "Black";
  return `${mover} played ${last.san}.`;
}

export function App() {
  const [prefs, setPrefs] = usePrefs();
  const game = useGame(prefs.sound);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [promotion, setPromotion] = useState<PendingPromotion | null>(null);
  const { step, flip } = game;

  useEffect(() => {
    // Browsers keep sound off until the reader has touched the page.
    const options = { once: true } as const;
    window.addEventListener("pointerdown", unlockSound, options);
    window.addEventListener("keydown", unlockSound, options);
    return () => {
      window.removeEventListener("pointerdown", unlockSound);
      window.removeEventListener("keydown", unlockSound);
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("dialog, input, textarea, [role='dialog']")) return;
      switch (event.key) {
        case "ArrowLeft":
          step("previous");
          break;
        case "ArrowRight":
          step("next");
          break;
        case "ArrowUp":
        case "Home":
          step("first");
          break;
        case "ArrowDown":
        case "End":
          step("last");
          break;
        case "f":
        case "F":
          flip();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, flip]);

  const lowTime = useCallback(() => {
    if (prefs.sound) playSound("low-time");
  }, [prefs.sound]);

  const snapshot = game.view.snapshot;
  const position = positionOf(game.view);
  if (snapshot === null || position === null) {
    return (
      <div className="app app--waiting">
        <p className="waiting" role="status">
          Setting up the board…
        </p>
      </div>
    );
  }

  const { human, engine, clock } = snapshot;
  const engineColour = human === "white" ? "black" : "white";
  const orientation = orientationOf(game.view);
  const playing = snapshot.status === "playing";
  const positionKey = `${snapshot.game_id}:${position.ply}:${game.resetCount}`;
  const activePromotion = promotion !== null && promotion.positionKey === positionKey ? promotion : null;
  const canMove =
    position.live && playing && snapshot.turn === human && !game.pending && activePromotion === null;

  const onBoardMove = (from: string, to: string) => {
    if (snapshot.legal.promotions.includes(from + to)) setPromotion({ positionKey, from, to });
    else game.move(from + to);
  };
  const onPromote = (piece: PromotionPiece) => {
    if (activePromotion === null) return;
    setPromotion(null);
    game.move(activePromotion.from + activePromotion.to + piece);
  };
  const onCancelPromotion = () => {
    setPromotion(null);
    game.resetBoard();
  };
  const startGame = (colour: ColourChoice, timeControl: string | null) => {
    setPrefs({ newGame: { human: colour, timeControl } });
    setDialogOpen(false);
    game.newGame(colour, timeControl);
  };

  const control = snapshot.time_controls.find((candidate) => candidate.id === snapshot.time_control);
  const caption = `${control ? timeControlLabel(control) : "Untimed"} · You play ${colourName(human)}`;

  const engineStrip = (
    <PlayerStrip
      name={ENGINE_NAME}
      colour={engineColour}
      status={engine.state === "thinking" ? "Thinking" : engine.state === "error" ? "Engine error" : ""}
      tone={engine.state === "thinking" ? "active" : engine.state === "error" ? "bad" : "quiet"}
      clockMs={clock ? clock[`${engineColour}_ms`] : null}
      clockRunning={clock?.running === engineColour}
      clockLabel="Engine's clock"
      clockTestId="clock-engine"
    />
  );
  const humanStrip = (
    <PlayerStrip
      name="You"
      colour={human}
      status={playing && snapshot.turn === human ? "Your move" : ""}
      tone="quiet"
      clockMs={clock ? clock[`${human}_ms`] : null}
      clockRunning={clock?.running === human}
      clockLabel="Your clock"
      clockTestId="clock-you"
      onLowTime={lowTime}
    />
  );
  const humanAtBottom = orientation === human;

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead__title">
          <h1 className="wordmark">chessgm</h1>
          <p className="masthead__caption" data-testid="caption">
            {caption}
          </p>
        </div>
        <div className="masthead__tools">
          {!game.view.connected && (
            <span className="tag" data-tone="note" role="status">
              Reconnecting
            </span>
          )}
          <IconButton
            label={prefs.enginePanel ? "Hide engine analysis" : "Show engine analysis"}
            pressed={prefs.enginePanel}
            onClick={() => setPrefs({ enginePanel: !prefs.enginePanel })}
          >
            <ChartLine weight="bold" />
          </IconButton>
          <IconButton
            label={prefs.sound ? "Mute sounds" : "Turn sounds on"}
            pressed={prefs.sound}
            onClick={() => setPrefs({ sound: !prefs.sound })}
          >
            {prefs.sound ? <SpeakerHigh weight="bold" /> : <SpeakerSlash weight="bold" />}
          </IconButton>
        </div>
      </header>

      <main className="table" data-eval={prefs.enginePanel ? "on" : "off"}>
        <section className="play" aria-label="Board">
          {humanAtBottom ? engineStrip : humanStrip}
          <div className="board-set">
            {prefs.enginePanel && <EvalBar score={engine.score} orientation={orientation} />}
            <div className="board-frame">
              <Board
                fen={position.fen}
                positionKey={positionKey}
                orientation={orientation}
                turn={position.fen.split(" ")[1] === "b" ? "black" : "white"}
                lastMove={position.lastMove}
                check={position.check}
                dests={canMove ? snapshot.legal.dests : null}
                movable={human}
                label={`Chess board. You play ${colourName(human)}.`}
                onMove={onBoardMove}
              />
              {activePromotion !== null && (
                <PromotionPicker
                  square={activePromotion.to}
                  colour={human}
                  orientation={orientation}
                  onChoose={onPromote}
                  onCancel={onCancelPromotion}
                />
              )}
            </div>
          </div>
          {humanAtBottom ? humanStrip : engineStrip}
        </section>

        <aside className="rail" aria-label="Game">
          {snapshot.result !== null && (
            <ResultBanner
              result={snapshot.result}
              human={human}
              busy={game.pending}
              onRematch={() => game.newGame(prefs.newGame.human, snapshot.time_control)}
              onNewGame={() => setDialogOpen(true)}
            />
          )}
          <MoveList
            plies={snapshot.plies}
            shownPly={position.ply}
            live={position.live}
            emptyText={human === "white" ? "Your move. White plays first." : "The engine plays first."}
            onGoto={game.goto}
            onStep={game.step}
          />
          {prefs.enginePanel && <EnginePanel engine={engine} onHide={() => setPrefs({ enginePanel: false })} />}
          <Actions
            canTakeback={snapshot.actions.takeback}
            canResign={snapshot.actions.resign}
            busy={game.pending}
            pgn={snapshot.pgn}
            fen={position.fen}
            onTakeback={game.takeback}
            onResign={game.resign}
            onFlip={game.flip}
            onNewGame={() => setDialogOpen(true)}
          />
          <p className="shortcuts">
            <kbd>←</kbd>
            <kbd>→</kbd> step through moves
            <kbd>F</kbd> flip
          </p>
        </aside>
      </main>

      {game.error !== null && (
        <p className="toast" role="alert">
          {errorText(game.error)}
        </p>
      )}
      <p className="visually-hidden" aria-live="polite" data-testid="announcer">
        {announcement(snapshot)}
      </p>

      <NewGameDialog
        open={dialogOpen}
        timeControls={snapshot.time_controls}
        initial={prefs.newGame}
        gameInProgress={playing && snapshot.plies.length > 0}
        onStart={startGame}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  );
}
