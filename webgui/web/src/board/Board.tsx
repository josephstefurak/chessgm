// The only file that touches chessground. It draws the position it is given and
// reports what the reader tried to move; whether that move stands is the server's call.

import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Key } from "chessground/types";
import { useEffect, useRef } from "react";
import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.cburnett.css";
import "./board.css";
import type { Colour } from "../api/types";

export interface BoardProps {
  fen: string;
  /** Changes whenever the board must be redrawn from `fen`. While it stays the
      same the board keeps what the reader just moved, so nothing snaps back. */
  positionKey: string;
  orientation: Colour;
  turn: Colour;
  lastMove: [string, string] | null;
  check: Colour | null;
  /** Where each of the reader's pieces may go, or null when nothing may be moved. */
  dests: Record<string, string[]> | null;
  movable: Colour;
  label: string;
  onMove: (from: string, to: string) => void;
}

function pieceAnimationMs(element: HTMLElement): number {
  const value = Number(getComputedStyle(element).getPropertyValue("--motion-piece-ms"));
  return Number.isFinite(value) ? value : 0;
}

export function Board(props: BoardProps) {
  const { fen, positionKey, orientation, turn, lastMove, check, dests, movable, label, onMove } = props;
  const element = useRef<HTMLDivElement>(null);
  const ground = useRef<Api | null>(null);
  const onMoveRef = useRef(onMove);
  useEffect(() => {
    onMoveRef.current = onMove;
  }, [onMove]);

  useEffect(() => {
    if (element.current === null) return;
    const duration = pieceAnimationMs(element.current);
    const api = Chessground(element.current, {
      coordinates: true,
      disableContextMenu: true,
      animation: { enabled: duration > 0, duration },
      highlight: { lastMove: true, check: true },
      premovable: { enabled: false },
      draggable: { showGhost: true },
      movable: {
        free: false,
        showDests: true,
        events: { after: (from, to) => onMoveRef.current(from, to) },
      },
    });
    ground.current = api;
    return () => {
      api.destroy();
      ground.current = null;
    };
  }, []);

  const lastMoveKey = lastMove?.join("") ?? "";
  useEffect(() => {
    ground.current?.set({
      fen,
      turnColor: turn,
      check: check ?? false,
      lastMove: lastMoveKey === "" ? [] : ([lastMoveKey.slice(0, 2), lastMoveKey.slice(2, 4)] as Key[]),
    });
    // `fen`, `turn`, `check` and the last move all follow from positionKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionKey]);

  useEffect(() => {
    ground.current?.set({ orientation });
  }, [orientation]);

  const destsKey = dests === null ? "" : JSON.stringify(dests);
  useEffect(() => {
    const map = new Map<Key, Key[]>();
    if (destsKey !== "") {
      for (const [from, targets] of Object.entries(JSON.parse(destsKey) as Record<string, string[]>)) {
        map.set(from as Key, targets as Key[]);
      }
    }
    // Without `color` chessground lets nothing be picked up.
    ground.current?.set({ movable: map.size > 0 ? { color: movable, dests: map } : { dests: map } });
    if (map.size === 0) ground.current?.cancelMove();
  }, [destsKey, movable, positionKey]);

  return (
    <div className="board">
      <div ref={element} className="board__ground" role="application" aria-label={label} />
    </div>
  );
}
