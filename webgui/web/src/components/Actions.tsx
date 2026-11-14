// What the reader can do to the game, and how to take it away with them.

import {
  ArrowCounterClockwise,
  ArrowsDownUp,
  Check,
  Copy,
  DownloadSimple,
  Flag,
  Plus,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { PGN_URL } from "../api/client";

const CONFIRM_MS = 3500;
const COPIED_MS = 1600;

interface Props {
  canTakeback: boolean;
  canResign: boolean;
  busy: boolean;
  pgn: string;
  fen: string;
  onTakeback: () => void;
  onResign: () => void;
  onFlip: () => void;
  onNewGame: () => void;
}

export function Actions(props: Props) {
  const { canTakeback, canResign, busy, pgn, fen, onTakeback, onResign, onFlip, onNewGame } = props;
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState<"pgn" | "fen" | null>(null);

  useEffect(() => {
    if (!confirming) return;
    const timer = window.setTimeout(() => setConfirming(false), CONFIRM_MS);
    return () => window.clearTimeout(timer);
  }, [confirming]);

  useEffect(() => {
    if (copied === null) return;
    const timer = window.setTimeout(() => setCopied(null), COPIED_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = (what: "pgn" | "fen", text: string) => {
    void navigator.clipboard.writeText(text).then(
      () => setCopied(what),
      () => setCopied(null),
    );
  };

  const resign = () => {
    if (confirming) {
      setConfirming(false);
      onResign();
    } else {
      setConfirming(true);
    }
  };

  return (
    <div className="actions">
      <div className="actions__main">
        <button type="button" className="button" onClick={onTakeback} disabled={!canTakeback || busy}>
          <ArrowCounterClockwise weight="bold" />
          Take back
        </button>
        <button
          type="button"
          className="button"
          data-tone={confirming ? "bad" : undefined}
          onClick={resign}
          disabled={!canResign || busy}
        >
          <Flag weight="bold" />
          {confirming ? "Confirm resign" : "Resign"}
        </button>
        <button type="button" className="button" onClick={onFlip}>
          <ArrowsDownUp weight="bold" />
          Flip board
        </button>
        <button type="button" className="button button--primary" onClick={onNewGame}>
          <Plus weight="bold" />
          New game
        </button>
      </div>

      <div className="actions__export">
        <button type="button" className="link-button" onClick={() => copy("pgn", pgn)}>
          {copied === "pgn" ? <Check weight="bold" /> : <Copy weight="bold" />}
          {copied === "pgn" ? "Copied" : "Copy PGN"}
        </button>
        <a className="link-button" href={PGN_URL} download>
          <DownloadSimple weight="bold" />
          Download PGN
        </a>
        <button type="button" className="link-button" onClick={() => copy("fen", fen)}>
          {copied === "fen" ? <Check weight="bold" /> : <Copy weight="bold" />}
          {copied === "fen" ? "Copied" : "Copy FEN"}
        </button>
      </div>
    </div>
  );
}
