/**
 * Circular readiness score visualization
 * Matches the spec: green >=85, amber >=60, red <60
 * Supports glow effect via drop-shadow
 */

import { t } from "../../styles/tokens";

interface ReadinessRingProps {
  score: number; // 0-100
  size?: number;
  label?: string;
}

function scoreColor(score: number): string {
  if (score >= 85) return t.green;
  if (score >= 60) return t.amber;
  return t.red;
}

export function ReadinessRing({ score, size = 120, label = "Readiness Score" }: ReadinessRingProps) {
  const strokeWidth = size <= 60 ? 4 : 6;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - score / 100);
  const color = scoreColor(score);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={t.surface3}
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-[600ms] ease"
          style={{ filter: `drop-shadow(0 0 8px ${color}40)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className={`font-extrabold font-mono leading-none ${
            size <= 60 ? "text-base" : "text-4xl"
          }`}
          style={{ color }}
        >
          {Math.round(score)}
        </span>
        {size > 60 && (
          <span className="text-[10px] text-mc-text-3 font-mono mt-0.5">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}

export { scoreColor };
