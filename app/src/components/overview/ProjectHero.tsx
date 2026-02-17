import { t } from "../../styles/tokens";

interface ProjectHeroProps {
  name: string;
  progress: number;
  completedItems: number;
  totalItems: number;
  milestoneCount: number;
  lastSession: string;
  costWeek: string;
}

export function ProjectHero({
  name,
  progress,
  completedItems,
  totalItems,
  milestoneCount,
  lastSession,
  costWeek,
}: ProjectHeroProps) {
  const radius = 23;
  const circumference = 2 * Math.PI * radius;

  const progressColor = progress >= 80 ? t.green : t.accent;

  return (
    <div className="flex items-center gap-5 px-5 py-[18px] rounded-xl bg-mc-surface-1 border border-mc-border-0">
      {/* Progress Ring */}
      <div className="relative w-14 h-14 shrink-0">
        <svg
          width="56"
          height="56"
          viewBox="0 0 56 56"
          className="-rotate-90"
        >
          <circle
            cx="28"
            cy="28"
            r={radius}
            fill="none"
            stroke={t.surface3}
            strokeWidth="4"
          />
          <circle
            cx="28"
            cy="28"
            r={radius}
            fill="none"
            stroke={progressColor}
            strokeWidth="4"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - progress / 100)}
            strokeLinecap="round"
            className="transition-[stroke-dashoffset] duration-500 ease-in-out"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-base font-extrabold font-mono text-mc-text-0">
          {progress}%
        </span>
      </div>

      {/* Project Info */}
      <div className="flex-1">
        <div className="text-lg font-extrabold text-mc-text-0 tracking-[-0.02em]">
          {name}
        </div>
        <div className="text-xs text-mc-text-2 mt-0.5">
          <span
            className={`font-semibold font-mono ${
              progress >= 80 ? "text-mc-green" : "text-mc-accent"
            }`}
          >
            {completedItems}
          </span>
          <span className="text-mc-text-3"> of </span>
          <span className="font-semibold text-mc-text-1 font-mono">
            {totalItems}
          </span>
          <span className="text-mc-text-3"> items complete across </span>
          <span className="font-semibold text-mc-text-1 font-mono">
            {milestoneCount}
          </span>
          <span className="text-mc-text-3"> milestones</span>
        </div>

        {/* Progress Bar */}
        <div className="mt-2.5 h-[5px] bg-mc-surface-3 rounded-sm overflow-hidden">
          <div
            className={`h-full rounded-sm transition-[width] duration-500 ease-in-out ${
              progress >= 80
                ? "bg-gradient-to-r from-mc-green to-[#2dd4a0]"
                : "bg-gradient-to-r from-mc-accent to-[#6d5bd0]"
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Quick Stats */}
      <div className="flex flex-col gap-1 items-end shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono text-mc-text-3 uppercase tracking-[0.05em]">
            Last Session
          </span>
          <span className="text-xs font-semibold font-mono text-mc-text-1">
            {lastSession}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono text-mc-text-3 uppercase tracking-[0.05em]">
            This Week
          </span>
          <span className="text-xs font-semibold font-mono text-mc-text-1">
            {costWeek}
          </span>
        </div>
      </div>
    </div>
  );
}
