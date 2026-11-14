// A clock that counts down smoothly between the server's snapshots. The server
// is the authority: this only draws, starting from the time it was last told.

import { useEffect, useRef, useState } from "react";
import { formatClock, LOW_TIME_MS } from "../format";

const TICK_MS = 100;

interface Props {
  ms: number;
  running: boolean;
  label: string;
  testId: string;
  /** Called once when a running clock drops into low time. */
  onLowTime?: (() => void) | undefined;
}

export function Clock(props: Props) {
  // Every new reading from the server starts the countdown afresh.
  return <Countdown key={`${props.ms}:${props.running}`} {...props} />;
}

function Countdown({ ms, running, label, testId, onLowTime }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const onLowTimeRef = useRef(onLowTime);
  useEffect(() => {
    onLowTimeRef.current = onLowTime;
  }, [onLowTime]);

  useEffect(() => {
    if (!running) return;
    const startedAt = performance.now();
    let warned = ms <= LOW_TIME_MS;
    const timer = window.setInterval(() => {
      const passed = performance.now() - startedAt;
      setElapsed(passed);
      if (!warned && ms - passed <= LOW_TIME_MS) {
        warned = true;
        onLowTimeRef.current?.();
      }
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [ms, running]);

  const shown = Math.max(0, ms - elapsed);
  return (
    <div
      className="clock"
      data-running={running}
      data-low={shown <= LOW_TIME_MS}
      role="timer"
      aria-label={label}
      data-testid={testId}
    >
      {formatClock(shown)}
    </div>
  );
}
