// What this browser remembers between visits. Nothing about the game itself:
// the server holds that. Everything read back is checked, never trusted.

import { useCallback, useState } from "react";
import type { ColourChoice } from "../api/types";

export interface Prefs {
  sound: boolean;
  enginePanel: boolean;
  newGame: { human: ColourChoice; timeControl: string | null };
}

export const DEFAULT_PREFS: Prefs = {
  sound: true,
  enginePanel: true,
  newGame: { human: "white", timeControl: null },
};

const KEY = "chessgm.prefs.v1";

export function parsePrefs(raw: string | null): Prefs {
  if (raw === null) return DEFAULT_PREFS;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return DEFAULT_PREFS;
  }
  if (typeof data !== "object" || data === null) return DEFAULT_PREFS;
  const record = data as Record<string, unknown>;
  const game = (typeof record.newGame === "object" && record.newGame !== null ? record.newGame : {}) as Record<
    string,
    unknown
  >;
  const human = game.human;
  const timeControl = game.timeControl;
  return {
    sound: typeof record.sound === "boolean" ? record.sound : DEFAULT_PREFS.sound,
    enginePanel: typeof record.enginePanel === "boolean" ? record.enginePanel : DEFAULT_PREFS.enginePanel,
    newGame: {
      human: human === "white" || human === "black" || human === "random" ? human : "white",
      timeControl: typeof timeControl === "string" && timeControl.length <= 16 ? timeControl : null,
    },
  };
}

function load(): Prefs {
  try {
    return parsePrefs(window.localStorage.getItem(KEY));
  } catch {
    return DEFAULT_PREFS; // storage can be blocked; the defaults still work
  }
}

export function usePrefs(): [Prefs, (change: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(load);
  const update = useCallback((change: Partial<Prefs>) => {
    setPrefs((current) => {
      const next = { ...current, ...change };
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // not being able to remember a preference is not worth interrupting a game
      }
      return next;
    });
  }, []);
  return [prefs, update];
}
