import { useState, useMemo } from "react";
import type { IntelligenceReport, HardcodedFinding, FileFreshness } from "../../types";
import { t } from "../../styles/tokens";
import { Icons } from "../ui/Icons";

interface TechDebtHeatmapProps {
  report: IntelligenceReport;
}

interface FileHeatEntry {
  filePath: string;
  heatScore: number;
  issuesScore: number;
  stalenessScore: number;
  criticalCount: number;
  warningCount: number;
  infoCount: number;
  freshnessCategory: FileFreshness["category"] | null;
  findings: HardcodedFinding[];
}

function computeHeatEntries(report: IntelligenceReport): FileHeatEntry[] {
  const totalFiles = Math.max(report.hardcoded.scanned_file_count, 1);

  // Group hardcoded findings by file
  const findingsByFile = new Map<string, HardcodedFinding[]>();
  for (const f of report.hardcoded.findings) {
    const existing = findingsByFile.get(f.file_path) || [];
    existing.push(f);
    findingsByFile.set(f.file_path, existing);
  }

  // Index freshness by file
  const freshnessByFile = new Map<string, FileFreshness>();
  for (const f of report.freshness.files) {
    freshnessByFile.set(f.file_path, f);
  }

  // Collect all unique file paths
  const allFiles = new Set<string>([
    ...findingsByFile.keys(),
    ...freshnessByFile.keys(),
  ]);

  const entries: FileHeatEntry[] = [];

  for (const filePath of allFiles) {
    const findings = findingsByFile.get(filePath) || [];
    const freshness = freshnessByFile.get(filePath) || null;

    const criticalCount = findings.filter((f) => f.severity === "critical").length;
    const warningCount = findings.filter((f) => f.severity === "warning").length;
    const infoCount = findings.filter((f) => f.severity === "info").length;

    // issues score: (critical*3 + warning*1) / total_files * 100
    const issuesScore = ((criticalCount * 3 + warningCount * 1) / totalFiles) * 100;

    // staleness score per file
    let stalenessScore = 0;
    if (freshness) {
      switch (freshness.category) {
        case "abandoned":
          stalenessScore = 100;
          break;
        case "stale":
          stalenessScore = 60;
          break;
        case "aging":
          stalenessScore = 20;
          break;
        default:
          stalenessScore = 0;
      }
    }

    // Heat formula: issues(60%) + staleness(40%)
    const heatScore = issuesScore * 0.6 + stalenessScore * 0.4;

    // Only include files that have some heat
    if (heatScore > 0) {
      entries.push({
        filePath,
        heatScore,
        issuesScore,
        stalenessScore,
        criticalCount,
        warningCount,
        infoCount,
        freshnessCategory: freshness?.category || null,
        findings,
      });
    }
  }

  // Sort by heat score descending
  entries.sort((a, b) => b.heatScore - a.heatScore);

  return entries;
}

function heatColor(score: number): string {
  if (score >= 70) return t.red;
  if (score >= 40) return t.amber;
  return t.green;
}

function heatBgClass(score: number): string {
  if (score >= 70) return "bg-mc-red";
  if (score >= 40) return "bg-mc-amber";
  return "bg-mc-green";
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
}

const severityStyles: Record<string, string> = {
  critical: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  warning: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  info: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

export function TechDebtHeatmap({ report }: TechDebtHeatmapProps) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);

  const allEntries = useMemo(() => computeHeatEntries(report), [report]);

  const filtered = useMemo(() => {
    if (!search) return allEntries;
    const q = search.toLowerCase();
    return allEntries.filter((e) => e.filePath.toLowerCase().includes(q));
  }, [allEntries, search]);

  const maxHeat = useMemo(
    () => Math.max(...filtered.map((e) => e.heatScore), 1),
    [filtered],
  );

  const displayed = showAll ? filtered.slice(0, 50) : filtered.slice(0, 20);

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Controls */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mc-text-3">
            {Icons.search({ size: 11 })}
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by file path..."
            className="w-full pl-8 pr-3 py-1.5 text-xs font-mono bg-mc-surface-2 border border-mc-border-1 rounded-lg text-mc-text-0 placeholder:text-mc-text-3 outline-none focus:border-mc-accent-border"
          />
        </div>
        <div className="flex bg-mc-surface-2 border border-mc-border-1 rounded-lg overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAll(false)}
            className={`px-3 py-1.5 text-[10px] font-mono font-semibold transition-colors ${
              !showAll
                ? "bg-mc-accent-muted text-mc-accent"
                : "text-mc-text-3 hover:text-mc-text-1"
            }`}
          >
            Top 20
          </button>
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className={`px-3 py-1.5 text-[10px] font-mono font-semibold transition-colors ${
              showAll
                ? "bg-mc-accent-muted text-mc-accent"
                : "text-mc-text-3 hover:text-mc-text-1"
            }`}
          >
            All files
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="text-[10px] text-mc-text-3 font-mono">
        {displayed.length} of {allEntries.length} files with debt
      </div>

      {/* Table */}
      {displayed.length === 0 ? (
        <div className="text-xs text-mc-text-3 font-mono text-center py-8">
          No tech debt detected
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Header */}
          <div className="flex items-center gap-3 px-3 py-2 text-[10px] font-mono font-bold text-mc-text-3 uppercase tracking-wider border-b border-mc-border-0">
            <span className="flex-1 min-w-0">File</span>
            <span className="w-32 text-center">Heat</span>
            <span className="w-12 text-right">Score</span>
          </div>

          {/* Rows */}
          {displayed.map((entry) => {
            const isExpanded = expandedFile === entry.filePath;
            return (
              <div key={entry.filePath}>
                <button
                  type="button"
                  onClick={() =>
                    setExpandedFile(isExpanded ? null : entry.filePath)
                  }
                  className="flex items-center gap-3 px-3 py-2 w-full text-left hover:bg-mc-surface-2 transition-colors cursor-pointer border-b border-mc-border-0"
                >
                  <span className="flex-1 min-w-0 text-xs font-mono text-mc-text-1 truncate">
                    {entry.filePath}
                  </span>
                  {/* Heat bar */}
                  <span className="w-32 flex items-center gap-2">
                    <span className="flex-1 h-2 rounded-full bg-mc-surface-3 overflow-hidden">
                      <span
                        className={`block h-full rounded-full ${heatBgClass(entry.heatScore)}`}
                        style={{
                          width: `${Math.min((entry.heatScore / maxHeat) * 100, 100)}%`,
                          opacity: 0.85,
                        }}
                      />
                    </span>
                  </span>
                  <span
                    className="w-12 text-right text-xs font-mono font-bold"
                    style={{ color: heatColor(entry.heatScore) }}
                  >
                    {Math.round(entry.heatScore)}
                  </span>
                </button>

                {/* Expanded findings */}
                {isExpanded && (
                  <div className="bg-mc-surface-0 border-b border-mc-border-0 px-4 py-3 animate-fade-in">
                    {/* Stats row */}
                    <div className="flex items-center gap-3 mb-2">
                      {entry.criticalCount > 0 && (
                        <span className={`mc-tag ${severityStyles.critical}`}>
                          {entry.criticalCount} critical
                        </span>
                      )}
                      {entry.warningCount > 0 && (
                        <span className={`mc-tag ${severityStyles.warning}`}>
                          {entry.warningCount} warning
                        </span>
                      )}
                      {entry.infoCount > 0 && (
                        <span className={`mc-tag ${severityStyles.info}`}>
                          {entry.infoCount} info
                        </span>
                      )}
                      {entry.freshnessCategory && (
                        <span className="mc-tag bg-mc-surface-2 text-mc-text-3 border border-mc-border-1">
                          {entry.freshnessCategory}
                        </span>
                      )}
                    </div>

                    {/* Individual findings */}
                    {entry.findings.length > 0 ? (
                      <div className="flex flex-col gap-1">
                        {entry.findings.map((f, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 text-[11px] font-mono py-1"
                          >
                            <span className="text-mc-text-3 w-10 flex-shrink-0 text-right">
                              :{f.line_number}
                            </span>
                            <span className={`mc-severity-tag ${severityStyles[f.severity]}`}>
                              {f.severity === "critical"
                                ? "CRIT"
                                : f.severity === "warning"
                                  ? "WARN"
                                  : "INFO"}
                            </span>
                            <span className="mc-tag bg-mc-surface-2 text-mc-text-3">
                              {f.category}
                            </span>
                            <span className="text-mc-text-2 truncate flex-1">
                              {truncate(f.matched_text, 60)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[11px] text-mc-text-3 font-mono">
                        No hardcoded findings — heat from staleness only
                      </div>
                    )}
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
