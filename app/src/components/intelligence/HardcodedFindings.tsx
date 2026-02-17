import { useState, useMemo } from "react";
import type { HardcodedFinding } from "../../types";
import { Icons } from "../ui/Icons";
import { SkeletonText } from "../ui/SkeletonLoader";

interface HardcodedFindingsProps {
  findings: HardcodedFinding[];
  isLoading?: boolean;
}

type SeverityFilter = "all" | "critical" | "warning" | "info";

const severityStyles: Record<"critical" | "warning" | "info", string> = {
  critical: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  warning: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  info: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

const categoryColors: Record<string, string> = {
  critical: "bg-mc-red-muted text-mc-red",
  warning: "bg-mc-amber-muted text-mc-amber",
  info: "bg-mc-surface-3 text-mc-text-3",
};

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
}

function severityOrder(s: string): number {
  if (s === "critical") return 0;
  if (s === "warning") return 1;
  return 2;
}

export function HardcodedFindings({ findings, isLoading }: HardcodedFindingsProps) {
  const [filter, setFilter] = useState<SeverityFilter>("all");
  const [search, setSearch] = useState("");
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const counts = useMemo(() => {
    const c = { all: findings.length, critical: 0, warning: 0, info: 0 };
    for (const f of findings) {
      c[f.severity]++;
    }
    return c;
  }, [findings]);

  const filtered = useMemo(() => {
    let result = findings;

    // Apply severity filter
    if (filter !== "all") {
      result = result.filter((f) => f.severity === filter);
    }

    // Apply search filter
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (f) =>
          f.file_path.toLowerCase().includes(q) ||
          f.matched_text.toLowerCase().includes(q) ||
          f.category.toLowerCase().includes(q),
      );
    }

    // Sort by severity (critical first)
    return [...result].sort(
      (a, b) => severityOrder(a.severity) - severityOrder(b.severity),
    );
  }, [findings, filter, search]);

  if (isLoading) {
    return (
      <div className="p-4">
        <SkeletonText lines={6} />
      </div>
    );
  }

  const filterPills: { key: SeverityFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "critical", label: "Critical" },
    { key: "warning", label: "Warning" },
    { key: "info", label: "Info" },
  ];

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Filter pills */}
        <div className="flex bg-mc-surface-2 border border-mc-border-1 rounded-lg overflow-hidden">
          {filterPills.map((pill) => (
            <button
              key={pill.key}
              type="button"
              onClick={() => setFilter(pill.key)}
              className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold transition-colors flex items-center gap-1 ${
                filter === pill.key
                  ? pill.key === "critical"
                    ? "bg-mc-red-muted text-mc-red"
                    : pill.key === "warning"
                      ? "bg-mc-amber-muted text-mc-amber"
                      : pill.key === "info"
                        ? "bg-mc-surface-3 text-mc-text-2"
                        : "bg-mc-accent-muted text-mc-accent"
                  : "text-mc-text-3 hover:text-mc-text-1"
              }`}
            >
              {pill.label}
              <span className="font-bold">{counts[pill.key]}</span>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="flex-1 relative min-w-[160px]">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mc-text-3">
            {Icons.search({ size: 11 })}
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search file, text, category..."
            className="w-full pl-8 pr-3 py-1.5 text-xs font-mono bg-mc-surface-2 border border-mc-border-1 rounded-lg text-mc-text-0 placeholder:text-mc-text-3 outline-none focus:border-mc-accent-border"
          />
        </div>
      </div>

      {/* Results count */}
      <div className="text-[10px] text-mc-text-3 font-mono">
        {filtered.length} finding{filtered.length !== 1 ? "s" : ""}
      </div>

      {/* Findings list */}
      {filtered.length === 0 ? (
        <div className="text-xs text-mc-text-3 font-mono text-center py-8">
          {findings.length === 0 ? "No hardcoded findings" : "No results match your filter"}
        </div>
      ) : (
        <div className="flex flex-col">
          {filtered.map((finding, idx) => {
            const isExpanded = expandedIndex === idx;
            return (
              <div key={`${finding.file_path}:${finding.line_number}:${idx}`}>
                <button
                  type="button"
                  onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                  className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-mc-surface-2 transition-colors cursor-pointer border-b border-mc-border-0"
                >
                  {/* Severity badge */}
                  <span className={`mc-severity-tag flex-shrink-0 ${severityStyles[finding.severity]}`}>
                    {finding.severity === "critical"
                      ? "CRIT"
                      : finding.severity === "warning"
                        ? "WARN"
                        : "INFO"}
                  </span>

                  {/* File:line */}
                  <span className="text-xs font-mono text-mc-text-1 flex-shrink-0 max-w-[200px] truncate">
                    {finding.file_path}
                    <span className="text-mc-text-3">:{finding.line_number}</span>
                  </span>

                  {/* Matched text */}
                  <span className="flex-1 text-[11px] font-mono text-mc-text-2 truncate min-w-0">
                    {truncate(finding.matched_text, 50)}
                  </span>

                  {/* Category tag */}
                  <span
                    className={`mc-tag flex-shrink-0 ${categoryColors[finding.severity] || categoryColors.info}`}
                  >
                    {finding.category}
                  </span>
                </button>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="bg-mc-surface-0 border-b border-mc-border-0 px-4 py-3 animate-fade-in flex flex-col gap-2">
                    {/* Full matched text */}
                    <div>
                      <span className="mc-label block mb-1">Matched Text</span>
                      <pre className="text-[11px] font-mono text-mc-text-1 bg-mc-surface-2 rounded-lg px-3 py-2 overflow-x-auto whitespace-pre-wrap break-all">
                        {finding.matched_text}
                      </pre>
                    </div>

                    {/* Suggestion */}
                    {finding.suggestion && (
                      <div>
                        <span className="mc-label block mb-1">Suggestion</span>
                        <p className="text-xs text-mc-text-2">
                          {finding.suggestion}
                        </p>
                      </div>
                    )}

                    {/* Meta */}
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`mc-tag ${severityStyles[finding.severity]}`}>
                        {finding.severity}
                      </span>
                      <span className="mc-tag bg-mc-surface-2 text-mc-text-3">
                        {finding.category}
                      </span>
                      <span className="text-[10px] font-mono text-mc-text-3">
                        {finding.file_path}:{finding.line_number}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
