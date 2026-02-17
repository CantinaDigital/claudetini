import { useState, useMemo } from "react";
import type { FreshnessReport, FileFreshness } from "../../types";
import { Tag } from "../ui/Tag";
import { Section } from "../ui/Section";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { t } from "../../styles/tokens";

interface CodeFreshnessProps {
  freshness: FreshnessReport;
  isLoading?: boolean;
}

const categoryConfig: Record<
  FileFreshness["category"],
  { color: string; bg: string; label: string }
> = {
  fresh: { color: t.green, bg: t.greenMuted, label: "Fresh" },
  aging: { color: t.amber, bg: t.amberMuted, label: "Aging" },
  stale: { color: t.red, bg: t.redMuted, label: "Stale" },
  abandoned: { color: t.red, bg: t.redMuted, label: "Abandoned" },
};

function StatBox({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
      <span
        className="text-lg font-extrabold font-mono leading-none"
        style={color ? { color } : undefined}
      >
        {value}
      </span>
      <span className="mc-label text-center">{label}</span>
    </div>
  );
}

function AgeDistributionBar({ distribution, total }: { distribution: FreshnessReport["age_distribution"]; total: number }) {
  if (total === 0) return null;

  const segments: Array<{ key: string; count: number; color: string; label: string }> = [
    { key: "fresh", count: distribution.fresh, color: t.green, label: "Fresh" },
    { key: "aging", count: distribution.aging, color: t.amber, label: "Aging" },
    { key: "stale", count: distribution.stale, color: t.red, label: "Stale" },
    { key: "abandoned", count: distribution.abandoned, color: "#dc2626", label: "Abandoned" },
  ];

  return (
    <div className="flex flex-col gap-2">
      {/* Bar */}
      <div className="h-3 rounded-full overflow-hidden flex bg-mc-surface-3">
        {segments.map((seg) => {
          const pct = (seg.count / total) * 100;
          if (pct === 0) return null;
          return (
            <div
              key={seg.key}
              className="h-full transition-all duration-300"
              style={{ width: `${pct}%`, backgroundColor: seg.color }}
              title={`${seg.label}: ${seg.count} files (${Math.round(pct)}%)`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap">
        {segments.map((seg) => (
          <div key={seg.key} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: seg.color }}
            />
            <span className="text-[10px] text-mc-text-3 font-mono">
              {seg.label}
              <span className="font-bold ml-1">{seg.count}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CodeFreshness({ freshness, isLoading = false }: CodeFreshnessProps) {
  const [showAll, setShowAll] = useState(false);

  const totalFiles = freshness.files.length;

  const medianAge = useMemo(() => {
    if (freshness.files.length === 0) return 0;
    const sorted = [...freshness.files]
      .map((f) => f.days_since_modified)
      .sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
      ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
      : sorted[mid];
  }, [freshness.files]);

  const sortedStaleFiles = useMemo(() => {
    const combined = [
      ...freshness.abandoned_files,
      ...freshness.stale_files,
      ...freshness.files.filter((f) => f.category === "aging"),
    ];

    // Deduplicate by file_path
    const seen = new Set<string>();
    const deduped = combined.filter((f) => {
      if (seen.has(f.file_path)) return false;
      seen.add(f.file_path);
      return true;
    });

    return deduped.sort((a, b) => b.days_since_modified - a.days_since_modified);
  }, [freshness]);

  const displayFiles = showAll ? sortedStaleFiles : sortedStaleFiles.slice(0, 30);

  if (isLoading) {
    return (
      <Section label="Code Freshness">
        <div className="p-4 flex flex-col gap-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </Section>
    );
  }

  if (totalFiles === 0) {
    return (
      <Section label="Code Freshness">
        <div className="py-6 px-4 text-center text-mc-text-3 text-xs">
          No freshness data available
        </div>
      </Section>
    );
  }

  const scoreColor = freshness.freshness_score >= 80 ? t.green : freshness.freshness_score >= 50 ? t.amber : t.red;

  return (
    <Section label="Code Freshness" right={`Score: ${Math.round(freshness.freshness_score)}%`}>
      {/* Stats row */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center gap-1 bg-mc-surface-2 rounded-lg p-3">
          <StatBox label="Files" value={totalFiles} />
          <div className="w-px h-8 bg-mc-border-1" />
          <StatBox label="Stale" value={freshness.stale_files.length} color={t.amber} />
          <div className="w-px h-8 bg-mc-border-1" />
          <StatBox label="Abandoned" value={freshness.abandoned_files.length} color={t.red} />
          <div className="w-px h-8 bg-mc-border-1" />
          <StatBox label="Median age" value={`${medianAge}d`} />
          <div className="w-px h-8 bg-mc-border-1" />
          <StatBox label="Freshness" value={`${Math.round(freshness.freshness_score)}%`} color={scoreColor} />
        </div>
      </div>

      {/* Age distribution bar */}
      <div className="px-4 pb-3">
        <AgeDistributionBar distribution={freshness.age_distribution} total={totalFiles} />
      </div>

      {/* File list */}
      {sortedStaleFiles.length > 0 && (
        <div className="border-t border-mc-border-0">
          <div className="flex items-center justify-between px-4 py-2.5">
            <span className="mc-label">
              {showAll ? "All files" : "Top 30 oldest files"}
            </span>
            {sortedStaleFiles.length > 30 && (
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="text-[10px] font-mono text-mc-accent hover:text-mc-text-0 cursor-pointer transition-colors"
              >
                {showAll ? "Show top 30" : `Show all (${sortedStaleFiles.length})`}
              </button>
            )}
          </div>

          <div className="px-4 pb-3">
            <div className="flex flex-col">
              {displayFiles.map((file, idx) => {
                const cfg = categoryConfig[file.category];
                const isAbandoned = file.category === "abandoned";

                return (
                  <div
                    key={file.file_path}
                    style={{ "--stagger-delay": `${idx * 0.015}s` } as React.CSSProperties}
                    className={`flex items-center gap-2.5 py-2 animate-slide-up [animation-delay:var(--stagger-delay)] [animation-fill-mode:both] ${
                      idx < displayFiles.length - 1 ? "border-b border-mc-border-0" : ""
                    } ${isAbandoned ? "bg-mc-red-muted/30 -mx-2 px-2 rounded" : ""}`}
                  >
                    <span className="text-xs font-mono text-mc-text-2 truncate flex-1 min-w-0">
                      {file.file_path}
                    </span>
                    <span className="text-[10px] font-mono text-mc-text-3 flex-shrink-0 w-12 text-right">
                      {file.days_since_modified}d
                    </span>
                    <span className="text-[10px] text-mc-text-3 truncate flex-shrink-0 max-w-[80px]">
                      {file.last_author}
                    </span>
                    <Tag color={cfg.color} bg={cfg.bg}>
                      {cfg.label}
                    </Tag>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </Section>
  );
}
