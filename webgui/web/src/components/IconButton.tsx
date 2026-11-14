import type { ReactNode } from "react";

interface Props {
  label: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  pressed?: boolean;
}

/** A square button that shows only an icon; `label` names it for everyone else. */
export function IconButton({ label, onClick, children, disabled = false, pressed }: Props) {
  return (
    <button
      type="button"
      className="icon-button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
