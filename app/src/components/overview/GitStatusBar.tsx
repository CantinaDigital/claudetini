import { Icons } from "../ui/Icons";

interface GitStatusBarProps {
  branch: string;
  uncommitted: number;
}

export function GitStatusBar({ branch, uncommitted }: GitStatusBarProps) {
  return (
    <div className="flex items-center gap-3 py-[9px] px-4 rounded-lg bg-mc-surface-0 border border-mc-border-0">
      {/* Branch */}
      <div className="flex items-center gap-1.5">
        <Icons.branch size={12} color="currentColor" />
        <span className="text-[11.5px] font-mono font-semibold text-mc-text-1">
          {branch}
        </span>
      </div>

      <div className="w-px h-3.5 bg-mc-border-1" />

      {/* Uncommitted */}
      <div className="flex items-center gap-[5px]">
        {uncommitted > 0 ? (
          <>
            <span className="text-[10px] font-bold font-mono text-mc-amber bg-mc-amber-muted py-[2px] px-1.5 rounded">
              {uncommitted}
            </span>
            <span className="text-[11px] text-mc-amber">
              uncommitted changes
            </span>
          </>
        ) : (
          <>
            <Icons.check size={10} color="currentColor" />
            <span className="text-[11px] text-mc-text-3">Clean working tree</span>
          </>
        )}
      </div>
    </div>
  );
}
