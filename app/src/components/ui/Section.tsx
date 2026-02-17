import type { ReactNode } from "react";

interface SectionProps {
  label?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Section({ label, right, children, className = "" }: SectionProps) {
  return (
    <div
      className={`bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden ${className}`}
    >
      {label && (
        <div className="flex justify-between items-center px-4 py-[11px] border-b border-mc-border-0">
          <span className="mc-label">{label}</span>
          {right && (
            <span className="text-[10px] text-mc-text-3 font-mono">{right}</span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
