import type { ReactNode, MouseEvent } from "react";

interface ButtonProps {
  children: ReactNode;
  primary?: boolean;
  danger?: boolean;
  green?: boolean;
  small?: boolean;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  className?: string;
  disabled?: boolean;
  title?: string;
}

export function Button({
  children,
  primary = false,
  danger = false,
  green = false,
  small = false,
  onClick,
  className = "",
  disabled = false,
  title,
}: ButtonProps) {
  const base = "inline-flex items-center gap-[5px] rounded-md font-sans font-semibold transition-all";
  const size = small ? "px-2.5 py-1 text-[11px]" : "px-3.5 py-1.5 text-xs";
  const variant = danger
    ? "bg-mc-red text-white border-none"
    : green
      ? "bg-mc-green text-white border-none"
      : primary
        ? "bg-mc-accent text-white border-none"
        : "bg-transparent border border-mc-border-2 text-mc-text-2";
  const state = disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer";

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${base} ${size} ${variant} ${state} ${className}`}
    >
      {children}
    </button>
  );
}
