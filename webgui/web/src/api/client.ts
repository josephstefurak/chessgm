// Everything the browser says to the server, and the one stream it listens to.

import { isSnapshot, type ColourChoice, type Snapshot } from "./types";

export type PostResult =
  | { ok: true; state: Snapshot }
  | { ok: false; error: string; state: Snapshot | null };

async function post(path: string, body: unknown): Promise<PostResult> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, error: "network", state: null };
  }
  const data: unknown = await response.json().catch(() => null);
  if (response.ok) {
    return isSnapshot(data) ? { ok: true, state: data } : { ok: false, error: "bad_response", state: null };
  }
  const record = typeof data === "object" && data !== null ? (data as Record<string, unknown>) : {};
  return {
    ok: false,
    error: typeof record.error === "string" ? record.error : "bad_response",
    state: isSnapshot(record.state) ? record.state : null,
  };
}

export const api = {
  newGame: (human: ColourChoice, timeControl: string | null) =>
    post("/api/game", { human, time_control: timeControl }),
  move: (gameId: string, ply: number, uci: string) => post("/api/move", { game_id: gameId, ply, uci }),
  takeback: (gameId: string, ply: number) => post("/api/takeback", { game_id: gameId, ply }),
  resign: (gameId: string) => post("/api/resign", { game_id: gameId }),
};

export const PGN_URL = "/api/pgn";

/**
 * Follow the game. The browser reconnects by itself if the stream drops, and the
 * server always sends the current state first, so nothing is replayed or missed.
 */
export function openStream(
  onState: (state: Snapshot) => void,
  onConnection: (connected: boolean) => void,
): () => void {
  const source = new EventSource("/api/events");
  source.addEventListener("open", () => onConnection(true));
  source.addEventListener("error", () => onConnection(false));
  source.addEventListener("state", (event) => {
    let data: unknown;
    try {
      data = JSON.parse((event as MessageEvent<string>).data);
    } catch {
      return;
    }
    if (isSnapshot(data)) onState(data);
  });
  return () => source.close();
}
