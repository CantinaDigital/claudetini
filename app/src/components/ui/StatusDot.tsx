import { t } from "../../styles/tokens";
import type { Status } from "../../types";

interface StatusDotProps {
  status: Status;
  size?: number;
}

export function StatusDot({ status, size = 6 }: StatusDotProps) {
  const color = status === "pass" ? t.green : status === "warn" ? t.amber : t.red;
  const glow =
    status === "pass"
      ? "rgba(52,211,153,0.4)"
      : status === "warn"
        ? "rgba(251,191,36,0.4)"
        : "rgba(248,113,113,0.5)";

  return (
    <div
      className="rounded-full shrink-0"
      style={{
        width: size,
        height: size,
        background: color,
        boxShadow: `0 0 ${size}px ${glow}`,
      }}
    />
  );
}
