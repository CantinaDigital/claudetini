/**
 * Skeleton loading components for progressive rendering
 * Phase 1 & 2: Show placeholders while data loads
 */

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: number;
}

export function Skeleton({ width = "100%", height = 20, borderRadius = 6 }: SkeletonProps) {
  return (
    <div
      className="bg-gradient-to-r from-mc-surface-2 via-mc-surface-3 to-mc-surface-2 bg-[length:200%_100%] animate-shimmer"
      style={{ width, height, borderRadius }}
    />
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={12}
          width={i === lines - 1 ? "70%" : "100%"}
        />
      ))}
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="py-3.5 px-[18px] rounded-[10px] bg-mc-surface-0 border border-mc-border-0">
      <div className="flex gap-2.5">
        <Skeleton width={14} height={14} />
        <div className="flex-1">
          <Skeleton width={100} height={10} />
          <div className="mt-2">
            <SkeletonText lines={2} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function SkeletonMilestone() {
  return (
    <div className="flex flex-col gap-2.5">
      <Skeleton width={200} height={16} />
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-2.5 py-2.5 px-3.5 rounded-lg bg-mc-surface-1"
        >
          <Skeleton width={20} height={20} borderRadius={4} />
          <Skeleton width="100%" height={12} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonSession() {
  return (
    <div className="flex flex-col gap-2 py-2.5 px-3.5">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1">
          <Skeleton width="80%" height={12} />
          <Skeleton width="50%" height={10} />
        </div>
      ))}
    </div>
  );
}
