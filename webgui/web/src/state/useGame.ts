// The game as the page uses it: the latest snapshot from the server, the reader's
// view of it, and the four things the reader can ask for.

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, openStream, type PostResult } from "../api/client";
import type { ColourChoice, Snapshot } from "../api/types";
import { playSound } from "../audio/sounds";
import { initialView, reduce, soundFor, type Step, type View } from "./reducer";

const ERROR_SHOWN_MS = 4000;

export interface Game {
  view: View;
  /** A request is on its way: the board is locked until it is answered. */
  pending: boolean;
  /** The code of the last refusal, shown briefly. */
  error: string | null;
  /** Changes whenever the board must be redrawn from the server's position. */
  resetCount: number;
  move: (uci: string) => void;
  newGame: (human: ColourChoice, timeControl: string | null) => void;
  takeback: () => void;
  resign: () => void;
  step: (step: Step) => void;
  goto: (ply: number) => void;
  flip: () => void;
  resetBoard: () => void;
}

export function useGame(soundOn: boolean): Game {
  const [view, dispatch] = useReducer(reduce, initialView);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetCount, setResetCount] = useState(0);

  const latest = useRef<Snapshot | null>(null);
  const soundRef = useRef(soundOn);
  const busy = useRef(false);
  useEffect(() => {
    soundRef.current = soundOn;
  }, [soundOn]);

  const accept = useCallback((snapshot: Snapshot) => {
    const previous = latest.current;
    if (previous === null || snapshot.version > previous.version || snapshot.game_id !== previous.game_id) {
      const sound = soundFor(previous, snapshot);
      if (sound !== null && soundRef.current) playSound(sound);
      latest.current = snapshot;
    }
    dispatch({ type: "snapshot", snapshot });
  }, []);

  useEffect(() => {
    return openStream(accept, (connected) => {
      if (connected) latest.current = null; // the server may have restarted
      dispatch({ type: "connection", connected });
    });
  }, [accept]);

  useEffect(() => {
    if (error === null) return;
    const timer = window.setTimeout(() => setError(null), ERROR_SHOWN_MS);
    return () => window.clearTimeout(timer);
  }, [error]);

  const resetBoard = useCallback(() => setResetCount((count) => count + 1), []);

  const send = useCallback(
    (request: (snapshot: Snapshot) => Promise<PostResult>) => {
      const snapshot = latest.current;
      if (snapshot === null || busy.current) return;
      busy.current = true;
      setPending(true);
      setError(null);
      void request(snapshot).then((result) => {
        busy.current = false;
        setPending(false);
        if (result.state !== null) accept(result.state);
        if (!result.ok) {
          setError(result.error);
          resetBoard(); // put back whatever the reader moved
        }
      });
    },
    [accept, resetBoard],
  );

  const move = useCallback(
    (uci: string) => send((snapshot) => api.move(snapshot.game_id, snapshot.plies.length, uci)),
    [send],
  );
  const newGame = useCallback(
    (human: ColourChoice, timeControl: string | null) => send(() => api.newGame(human, timeControl)),
    [send],
  );
  const takeback = useCallback(
    () => send((snapshot) => api.takeback(snapshot.game_id, snapshot.plies.length)),
    [send],
  );
  const resign = useCallback(() => send((snapshot) => api.resign(snapshot.game_id)), [send]);
  const step = useCallback((to: Step) => dispatch({ type: "step", step: to }), []);
  const goto = useCallback((ply: number) => dispatch({ type: "goto", ply }), []);
  const flip = useCallback(() => dispatch({ type: "flip" }), []);

  return { view, pending, error, resetCount, move, newGame, takeback, resign, step, goto, flip, resetBoard };
}
