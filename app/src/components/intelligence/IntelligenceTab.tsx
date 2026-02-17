import { useCallback, useEffect, useMemo, useState } from "react";
import type { IntelligenceReport, CategoryScore, HardcodedFinding, FileFreshness } from "../../types";
import { api, isBackendConnected } from "../../api/backend";
import { useProjectManager } from "../../managers/projectManager";
import { t } from "../../styles/tokens";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";

// ── Constants ────────────────────────────────────────────────────────

const CACHE_KEY = "cantina:intelligence-report";
const CACHE_MAX_AGE_MS = 60 * 60 * 1000; // 1 hour

const DIM_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  hardcoded: { label: "Hardcoded", icon: "lock", color: t.red },
  dependency: { label: "Dependencies", icon: "folder", color: t.amber },
  integration: { label: "Integrations", icon: "bolt", color: t.cyan },
  freshness: { label: "Freshness", icon: "refresh", color: t.green },
  feature: { label: "Features", icon: "check", color: t.accent },
};

const SEV_STYLES: Record<string, string> = {
  critical: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  high: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  warning: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  info: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

// ── Cache helpers ────────────────────────────────────────────────────

interface CachedReport {
  projectPath: string;
  timestamp: number;
  report: IntelligenceReport;
}

function getCachedReport(projectPath: string): IntelligenceReport | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cached: CachedReport = JSON.parse(raw);
    if (cached.projectPath !== projectPath) return null;
    if (Date.now() - cached.timestamp > CACHE_MAX_AGE_MS) return null;
    return cached.report;
  } catch {
    return null;
  }
}

function setCachedReport(projectPath: string, report: IntelligenceReport): void {
  try {
    const cached: CachedReport = { projectPath, timestamp: Date.now(), report };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cached));
  } catch { /* localStorage full — ignore */ }
}

// ── Data transforms ──────────────────────────────────────────────────

interface HeatEntry {
  filePath: string;
  heat: number;
  dims: string[]; // which dimensions contribute
  criticalCount: number;
  warningCount: number;
  freshnessCategory: string | null;
}

function computeHeatmap(report: IntelligenceReport): HeatEntry[] {
  const totalFiles = Math.max(report.hardcoded.scanned_file_count, 1);
  const findingsByFile = new Map<string, HardcodedFinding[]>();
  for (const f of report.hardcoded.findings) {
    const existing = findingsByFile.get(f.file_path) || [];
    existing.push(f);
    findingsByFile.set(f.file_path, existing);
  }

  const freshnessByFile = new Map<string, FileFreshness>();
  for (const f of report.freshness.files) {
    freshnessByFile.set(f.file_path, f);
  }

  const allFiles = new Set([...findingsByFile.keys(), ...freshnessByFile.keys()]);
  const entries: HeatEntry[] = [];

  for (const filePath of allFiles) {
    const findings = findingsByFile.get(filePath) || [];
    const freshness = freshnessByFile.get(filePath) || null;
    const critCount = findings.filter(f => f.severity === "critical").length;
    const warnCount = findings.filter(f => f.severity === "warning").length;

    const issuesScore = ((critCount * 3 + warnCount * 1) / totalFiles) * 100;
    let stalenessScore = 0;
    if (freshness) {
      switch (freshness.category) {
        case "abandoned": stalenessScore = 100; break;
        case "stale": stalenessScore = 60; break;
        case "aging": stalenessScore = 20; break;
      }
    }

    const heat = issuesScore * 0.6 + stalenessScore * 0.4;
    if (heat > 0) {
      const dims: string[] = [];
      if (findings.length > 0) dims.push("hardcoded");
      if (stalenessScore > 0) dims.push("freshness");
      entries.push({
        filePath,
        heat,
        dims,
        criticalCount: critCount,
        warningCount: warnCount,
        freshnessCategory: freshness?.category || null,
      });
    }
  }

  entries.sort((a, b) => b.heat - a.heat);
  return entries;
}

interface HardcodedByType {
  type: string;
  count: number;
  sev: string;
  example: string;
}

function groupHardcodedByType(findings: HardcodedFinding[]): HardcodedByType[] {
  const groups = new Map<string, HardcodedFinding[]>();
  for (const f of findings) {
    const key = f.category.toUpperCase();
    const existing = groups.get(key) || [];
    existing.push(f);
    groups.set(key, existing);
  }
  const result: HardcodedByType[] = [];
  for (const [type, items] of groups) {
    const maxSev = items.some(i => i.severity === "critical") ? "critical"
      : items.some(i => i.severity === "warning") ? "warning" : "info";
    result.push({ type, count: items.length, sev: maxSev, example: items[0].matched_text });
  }
  result.sort((a, b) => b.count - a.count);
  return result;
}

function getDimScores(report: IntelligenceReport): CategoryScore[] {
  if (report.category_scores && report.category_scores.length > 0) {
    return report.category_scores;
  }
  // Client-side fallback
  const hcCrit = report.hardcoded.findings.filter(f => f.severity === "critical").length;
  const hcWarn = report.hardcoded.findings.filter(f => f.severity === "warning").length;
  const hcScore = Math.max(0, 100 - hcCrit * 10 - hcWarn * 2);

  let depPenalty = 0;
  let depCrit = 0;
  let depWarn = 0;
  let depCount = 0;
  for (const eco of report.dependencies) {
    for (const v of eco.vulnerabilities) {
      depCount++;
      if (v.severity === "critical") { depCrit++; depPenalty += 15; }
      else { depWarn++; depPenalty += 3; }
    }
    for (const d of eco.outdated) {
      depCount++;
      if (d.update_severity === "major") { depWarn++; depPenalty += 5; }
      else if (d.update_severity === "minor") depPenalty += 1;
    }
  }
  const depScore = Math.max(0, 100 - depPenalty);

  const totalInt = report.integrations.integrations.length;
  const intScore = totalInt > 0 ? Math.min(100, 50 + totalInt * 5) : 50;
  const freshScore = report.freshness.freshness_score;
  const featScore = report.features.total_features > 0
    ? Math.min(100, 50 + report.features.total_features * 2) : 50;

  const grade = (s: number) => s >= 90 ? "A" : s >= 80 ? "B" : s >= 70 ? "C" : s >= 60 ? "D" : "F";

  return [
    { category: "hardcoded", score: hcScore, grade: grade(hcScore), finding_count: report.hardcoded.findings.length, critical_count: hcCrit, warning_count: hcWarn },
    { category: "dependency", score: depScore, grade: grade(depScore), finding_count: depCount, critical_count: depCrit, warning_count: depWarn },
    { category: "integration", score: intScore, grade: grade(intScore), finding_count: totalInt, critical_count: 0, warning_count: 0 },
    { category: "freshness", score: freshScore, grade: grade(freshScore), finding_count: report.freshness.stale_files.length + report.freshness.abandoned_files.length, critical_count: report.freshness.abandoned_files.length, warning_count: report.freshness.stale_files.length },
    { category: "feature", score: featScore, grade: grade(featScore), finding_count: report.features.total_features, critical_count: 0, warning_count: 0 },
  ];
}

function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
}

// ── Score Ring SVG ───────────────────────────────────────────────────

function ScoreRing({ score, size = 72 }: { score: number; size?: number }) {
  const strokeWidth = 5;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - score / 100);
  const color = score >= 85 ? t.green : score >= 60 ? t.amber : t.red;
  const grade = score >= 90 ? "A" : score >= 80 ? "B" : score >= 70 ? "C" : score >= 60 ? "D" : "F";

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={t.surface3} strokeWidth={strokeWidth} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-[600ms] ease"
          style={{ filter: `drop-shadow(0 0 8px ${color}40)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-extrabold font-mono leading-none" style={{ color }}>{grade}</span>
        <span className="text-[10px] font-mono text-mc-text-3 mt-0.5">{Math.round(score)}</span>
      </div>
    </div>
  );
}

// ── Dimension Icon ───────────────────────────────────────────────────

function DimIcon({ dim, size = 14 }: { dim: string; size?: number }) {
  const iconMap: Record<string, typeof Icons.lock> = {
    lock: Icons.lock,
    folder: Icons.folder,
    bolt: Icons.bolt,
    refresh: Icons.refresh,
    check: Icons.check,
  };
  const cfg = DIM_CONFIG[dim];
  const Icon = cfg ? iconMap[cfg.icon] : null;
  return Icon ? <>{Icon({ size, color: cfg.color })}</> : null;
}

// ── Props ────────────────────────────────────────────────────────────

interface IntelligenceTabProps {
  onFix?: (source: string, description: string) => void;
}

// ── Main Component ───────────────────────────────────────────────────

export default function IntelligenceTab({ onFix }: IntelligenceTabProps) {
  const projectPath = useProjectManager((s) => s.currentProject?.path) ?? "";

  const [report, setReport] = useState<IntelligenceReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load on mount
  useEffect(() => {
    if (!projectPath) return;
    const cached = getCachedReport(projectPath);
    if (cached) { setReport(cached); return; }
    if (!isBackendConnected()) return;

    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const summary = await api.getIntelligenceSummary(projectPath);
        if (cancelled) return;
        if (summary) {
          const fullReport = await api.getIntelligence(projectPath);
          if (cancelled) return;
          setReport(fullReport);
          setCachedReport(projectPath, fullReport);
        }
      } catch {
        if (!cancelled) setReport(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [projectPath]);

  // Scan handler
  const handleScan = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.scanIntelligence(projectPath);
      setReport(result);
      setCachedReport(projectPath, result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setIsLoading(false);
    }
  }, [projectPath]);

  // Derived data
  const dimScores = useMemo(() => report ? getDimScores(report) : [], [report]);
  const heatEntries = useMemo(() => report ? computeHeatmap(report) : [], [report]);
  const hardcodedByType = useMemo(
    () => report ? groupHardcodedByType(report.hardcoded.findings) : [],
    [report],
  );

  // Fix handlers
  const handleDimFix = (dim: string) => {
    if (!onFix) return;
    const descriptions: Record<string, string> = {
      hardcoded: "Fix all hardcoded values: remove placeholders, extract env vars, replace magic numbers with named constants",
      dependency: "Update all outdated dependencies and resolve vulnerability advisories",
      freshness: "Review and update stale/abandoned files, remove dead code",
      feature: "Add roadmap tracking for untracked features, reduce coupling in highly-coupled modules",
      integration: "Document and verify all external integrations",
    };
    onFix(dim, descriptions[dim] || `Fix all ${dim} issues`);
  };

  const handleIssueFix = (issue: IntelligenceReport["top_issues"][0]) => {
    if (!onFix) return;
    const loc = issue.file_path ? ` in ${issue.file_path}${issue.line_number ? `:${issue.line_number}` : ""}` : "";
    onFix(issue.dim || "intelligence", `Fix: ${issue.issue}${loc}`);
  };

  const handleFixAll = () => {
    if (!onFix || !report) return;
    const issueList = report.top_issues.slice(0, 5).map(i => i.issue).join("; ");
    onFix("intelligence", `Fix all priority issues: ${issueList}`);
  };

  const handleGetAnA = () => {
    if (!onFix) return;
    onFix("intelligence", "Analyze which fixes would push the intelligence score above 90 and implement them");
  };

  // Loading skeleton
  if (isLoading && !report) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  // Empty state
  if (!report && !isLoading && !error) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-text-3">{Icons.search({ size: 32 })}</span>
          <p className="text-sm text-mc-text-2 font-mono text-center">
            No intelligence data. Run a scan to get started.
          </p>
          <Button primary onClick={handleScan}>Scan Now</Button>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !report) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-red">{Icons.alert({ size: 32 })}</span>
          <p className="text-sm text-mc-red font-mono text-center">{error}</p>
          <Button onClick={handleScan}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!report) return null;

  const critCount = report.top_issues.filter(i => i.severity === "critical" || i.severity === "high").length;
  const warnCount = report.top_issues.filter(i => i.severity === "warning").length;
  const topHeatFiles = heatEntries.slice(0, 8);
  const maxHeat = Math.max(...topHeatFiles.map(e => e.heat), 1);

  // Freshness stats
  const { age_distribution, freshness_score } = report.freshness;
  const totalFreshnessFiles = report.freshness.files.length;
  const medianAge = totalFreshnessFiles > 0
    ? (() => {
        const sorted = [...report.freshness.files].map(f => f.days_since_modified).sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 === 0 ? Math.round((sorted[mid - 1] + sorted[mid]) / 2) : sorted[mid];
      })()
    : 0;

  // Integration summary
  const servicesByType = new Map<string, number>();
  for (const pt of report.integrations.integrations) {
    const label = pt.integration_type === "external_api" ? "API"
      : pt.integration_type === "internal_route" ? "Route"
      : pt.integration_type === "sdk_import" ? "SDK" : "DB";
    servicesByType.set(label, (servicesByType.get(label) || 0) + 1);
  }

  // Dep summary
  const totalVulns = report.dependencies.reduce((s, e) => s + e.vulnerabilities.length, 0);
  const totalOutdated = report.dependencies.reduce((s, e) => s + e.outdated.length, 0);

  return (
    <div className="max-w-[960px] mx-auto p-6 flex flex-col gap-5">
      {/* ════════════════════════════════════════════════════════════════ */}
      {/* TIER 1 — Executive Summary                                     */}
      {/* ════════════════════════════════════════════════════════════════ */}
      <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl p-5">
        <div className="flex items-start gap-5">
          {/* Score hero */}
          <div className="flex flex-col items-center gap-1 flex-shrink-0">
            <ScoreRing score={report.overall_score} />
          </div>

          {/* Dimension cards */}
          <div className="flex-1 grid grid-cols-5 gap-2 min-w-0">
            {dimScores.map((dim) => {
              const cfg = DIM_CONFIG[dim.category];
              if (!cfg) return null;
              const scoreColor = dim.score >= 85 ? t.green : dim.score >= 60 ? t.amber : t.red;
              return (
                <div
                  key={dim.category}
                  className="bg-mc-surface-2 border border-mc-border-0 rounded-lg p-3 flex flex-col gap-2"
                >
                  {/* Top color bar */}
                  <div className="h-0.5 rounded-full -mt-1 -mx-1" style={{ backgroundColor: cfg.color, opacity: 0.6 }} />
                  {/* Icon + label */}
                  <div className="flex items-center gap-1.5">
                    <DimIcon dim={dim.category} size={12} />
                    <span className="text-[10px] font-semibold text-mc-text-1 truncate">{cfg.label}</span>
                  </div>
                  {/* Score */}
                  <div className="flex items-baseline gap-1">
                    <span className="text-lg font-extrabold font-mono leading-none" style={{ color: scoreColor }}>
                      {dim.score}
                    </span>
                    <span className="text-[9px] text-mc-text-3 font-mono">/100</span>
                  </div>
                  {/* Issue count */}
                  <div className="text-[10px] font-mono text-mc-text-3">
                    {dim.finding_count} {dim.finding_count === 1 ? "issue" : "issues"}
                    {dim.critical_count > 0 && (
                      <span className="text-mc-red ml-1">{dim.critical_count} crit</span>
                    )}
                  </div>
                  {/* Top finding */}
                  {dim.top_finding && (
                    <p className="text-[9px] text-mc-text-3 leading-snug truncate" title={dim.top_finding}>
                      {dim.top_finding}
                    </p>
                  )}
                  {/* Progress bar */}
                  <div className="h-1 rounded-full bg-mc-surface-3 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${dim.score}%`, backgroundColor: scoreColor }}
                    />
                  </div>
                  {/* Fix button */}
                  {onFix && dim.finding_count > 0 && dim.category !== "integration" && (
                    <button
                      type="button"
                      onClick={() => handleDimFix(dim.category)}
                      className="text-[9px] font-mono text-mc-accent hover:text-mc-text-0 transition-colors cursor-pointer text-left"
                    >
                      Fix
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Scan controls row */}
        <div className="flex items-center gap-3 mt-4 pt-3 border-t border-mc-border-0">
          <span className="text-[10px] text-mc-text-3 font-mono">
            {formatRelativeTime(report.generated_at)}
          </span>
          {report.total_files_scanned != null && report.total_files_scanned > 0 && (
            <span className="text-[10px] text-mc-text-3 font-mono">
              {report.total_files_scanned} files scanned
            </span>
          )}
          <div className="flex-1" />
          {onFix && report.overall_score < 90 && (
            <Button small onClick={handleGetAnA}>
              Get an A
            </Button>
          )}
          <Button small primary onClick={handleScan} disabled={isLoading}>
            {isLoading ? (
              <span className="flex items-center gap-1">
                <span className="animate-spin inline-block">{Icons.refresh({ size: 10 })}</span>
                Scanning...
              </span>
            ) : "Scan"}
          </Button>
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════ */}
      {/* TIER 2 — The Story                                             */}
      {/* ════════════════════════════════════════════════════════════════ */}
      <div className="grid gap-4" style={{ gridTemplateColumns: "3fr 2fr" }}>
        {/* Priority Issues */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-red">{Icons.alert({ size: 13 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Priority Issues</span>
            {critCount > 0 && (
              <span className="mc-tag bg-mc-red-muted text-mc-red border border-mc-red-border text-[9px]">
                {critCount} crit
              </span>
            )}
            {warnCount > 0 && (
              <span className="mc-tag bg-mc-amber-muted text-mc-amber border border-mc-amber-border text-[9px]">
                {warnCount} warn
              </span>
            )}
            {onFix && report.top_issues.length > 0 && (
              <button
                type="button"
                onClick={handleFixAll}
                className="text-[9px] font-mono text-mc-accent hover:text-mc-text-0 cursor-pointer transition-colors"
              >
                Fix All
              </button>
            )}
          </div>
          <div className="flex flex-col max-h-[400px] overflow-y-auto">
            {report.top_issues.length === 0 ? (
              <div className="p-6 text-center text-xs text-mc-text-3 font-mono">
                No priority issues found
              </div>
            ) : (
              report.top_issues.map((issue, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 px-4 py-2.5 border-b border-mc-border-0 last:border-b-0 hover:bg-mc-surface-2 transition-colors"
                >
                  {/* Severity tag */}
                  <span className={`mc-tag flex-shrink-0 text-[9px] ${SEV_STYLES[issue.severity] || SEV_STYLES.info}`}>
                    {issue.severity === "critical" ? "CRIT" : issue.severity === "high" ? "HIGH" : issue.severity === "warning" ? "WARN" : "INFO"}
                  </span>
                  {/* Issue text */}
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] font-mono text-mc-text-1 leading-snug">
                      {truncate(issue.issue, 80)}
                    </p>
                    {issue.file_path && (
                      <span className="text-[9px] font-mono text-mc-text-3 mt-0.5 block truncate">
                        {issue.file_path}{issue.line_number ? `:${issue.line_number}` : ""}
                      </span>
                    )}
                  </div>
                  {/* Type tag */}
                  {issue.issue_type && (
                    <span className="mc-tag bg-mc-surface-2 text-mc-text-3 border border-mc-border-1 text-[8px] flex-shrink-0">
                      {issue.issue_type}
                    </span>
                  )}
                  {/* Fix button */}
                  {onFix && (
                    <button
                      type="button"
                      onClick={() => handleIssueFix(issue)}
                      className="text-[9px] font-mono text-mc-accent hover:text-mc-text-0 cursor-pointer transition-colors flex-shrink-0"
                    >
                      Fix
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Debt Heatmap */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-amber">{Icons.alert({ size: 13 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Debt Heatmap</span>
            <span className="text-[10px] font-mono text-mc-text-3">{heatEntries.length} files</span>
          </div>

          {/* Treemap blocks */}
          {heatEntries.length > 0 && (
            <div className="px-4 pt-3 pb-2">
              <div className="flex flex-wrap gap-1">
                {heatEntries.slice(0, 20).map((entry) => {
                  const minSize = 16;
                  const maxSize = 40;
                  const normalized = Math.min(entry.heat / maxHeat, 1);
                  const size = Math.round(minSize + normalized * (maxSize - minSize));
                  const bg = entry.heat >= 70 ? t.red : entry.heat >= 40 ? t.amber : t.green;
                  return (
                    <div
                      key={entry.filePath}
                      className="rounded-sm opacity-80 hover:opacity-100 transition-opacity cursor-default"
                      style={{
                        width: size,
                        height: size,
                        backgroundColor: bg,
                        opacity: 0.3 + normalized * 0.7,
                      }}
                      title={`${entry.filePath}: heat ${Math.round(entry.heat)}`}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Hot files list */}
          <div className="flex flex-col max-h-[260px] overflow-y-auto">
            {topHeatFiles.map((entry) => (
              <div
                key={entry.filePath}
                className="flex items-center gap-2 px-4 py-1.5 border-b border-mc-border-0 last:border-b-0"
              >
                <span className="text-[10px] font-mono text-mc-text-2 truncate flex-1 min-w-0">
                  {entry.filePath}
                </span>
                {/* Heat bar */}
                <span className="w-16 flex items-center">
                  <span className="flex-1 h-1.5 rounded-full bg-mc-surface-3 overflow-hidden">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${Math.min((entry.heat / maxHeat) * 100, 100)}%`,
                        backgroundColor: entry.heat >= 70 ? t.red : entry.heat >= 40 ? t.amber : t.green,
                      }}
                    />
                  </span>
                </span>
                {/* Dimension dots */}
                <div className="flex items-center gap-0.5">
                  {entry.dims.map((d) => (
                    <span
                      key={d}
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: DIM_CONFIG[d]?.color || t.text3 }}
                      title={d}
                    />
                  ))}
                </div>
                <span
                  className="text-[10px] font-mono font-bold w-6 text-right"
                  style={{ color: entry.heat >= 70 ? t.red : entry.heat >= 40 ? t.amber : t.green }}
                >
                  {Math.round(entry.heat)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════ */}
      {/* TIER 3 — Deep Dives                                            */}
      {/* ════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-2 gap-4">
        {/* Hardcoded by Type */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-red">{Icons.lock({ size: 12 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Hardcoded by Type</span>
            <span className="text-[10px] font-mono text-mc-text-3">
              {report.hardcoded.findings.length} total
            </span>
          </div>
          <div className="p-4 flex flex-col gap-2">
            {hardcodedByType.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">
                No hardcoded findings
              </div>
            ) : (
              hardcodedByType.map((group) => {
                const maxCount = Math.max(...hardcodedByType.map(g => g.count), 1);
                const barColor = group.sev === "critical" ? t.red : group.sev === "warning" ? t.amber : t.text3;
                return (
                  <div key={group.type} className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-mc-text-2 w-24 truncate flex-shrink-0">
                      {group.type}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-mc-surface-3 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${(group.count / maxCount) * 100}%`,
                          backgroundColor: barColor,
                          opacity: 0.75,
                        }}
                      />
                    </div>
                    <span className="text-[10px] font-mono font-bold text-mc-text-2 w-6 text-right">
                      {group.count}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Integrations */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-cyan">{Icons.bolt({ size: 12 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Integrations</span>
            <span className="text-[10px] font-mono text-mc-text-3">
              {report.integrations.services_detected.length} services
            </span>
          </div>
          <div className="p-4">
            {/* Service cards */}
            {report.integrations.services_detected.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">
                No integrations detected
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2 mb-3">
                {report.integrations.services_detected.slice(0, 6).map((svc) => (
                  <div
                    key={svc.service_name}
                    className="bg-mc-surface-2 border border-mc-border-0 rounded-lg px-2.5 py-2"
                  >
                    <span className="text-[10px] font-semibold text-mc-text-0 block truncate">
                      {svc.service_name}
                    </span>
                    <span className="text-[9px] font-mono text-mc-text-3">
                      {svc.count} points
                    </span>
                  </div>
                ))}
              </div>
            )}
            {/* Type distribution bar */}
            {servicesByType.size > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                {Array.from(servicesByType.entries()).map(([label, count]) => {
                  const colorMap: Record<string, string> = { API: t.red, Route: t.cyan, SDK: t.green, DB: t.accent };
                  return (
                    <div key={label} className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colorMap[label] || t.text3 }} />
                      <span className="text-[9px] font-mono text-mc-text-3">
                        {label} <span className="font-bold">{count}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Code Freshness */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-green">{Icons.refresh({ size: 12 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Code Freshness</span>
            <span className="text-[10px] font-mono text-mc-text-3">
              {Math.round(freshness_score)}%
            </span>
          </div>
          <div className="p-4">
            {/* 4-stat strip */}
            <div className="flex items-center gap-1 mb-3 bg-mc-surface-2 rounded-lg p-2.5">
              <div className="flex-1 text-center">
                <span className="text-sm font-extrabold font-mono text-mc-text-0 block">{totalFreshnessFiles}</span>
                <span className="text-[8px] text-mc-text-3 font-mono">Files</span>
              </div>
              <div className="w-px h-6 bg-mc-border-1" />
              <div className="flex-1 text-center">
                <span className="text-sm font-extrabold font-mono block" style={{ color: t.amber }}>
                  {report.freshness.stale_files.length}
                </span>
                <span className="text-[8px] text-mc-text-3 font-mono">Stale</span>
              </div>
              <div className="w-px h-6 bg-mc-border-1" />
              <div className="flex-1 text-center">
                <span className="text-sm font-extrabold font-mono block" style={{ color: t.red }}>
                  {report.freshness.abandoned_files.length}
                </span>
                <span className="text-[8px] text-mc-text-3 font-mono">Abandoned</span>
              </div>
              <div className="w-px h-6 bg-mc-border-1" />
              <div className="flex-1 text-center">
                <span className="text-sm font-extrabold font-mono text-mc-text-0 block">{medianAge}d</span>
                <span className="text-[8px] text-mc-text-3 font-mono">Median</span>
              </div>
            </div>
            {/* Age distribution bar */}
            {totalFreshnessFiles > 0 && (
              <div>
                <div className="h-2.5 rounded-full overflow-hidden flex bg-mc-surface-3">
                  {[
                    { key: "fresh", count: age_distribution.fresh, color: t.green },
                    { key: "aging", count: age_distribution.aging, color: t.amber },
                    { key: "stale", count: age_distribution.stale, color: t.red },
                    { key: "abandoned", count: age_distribution.abandoned, color: "#dc2626" },
                  ].map((seg) => {
                    const pct = (seg.count / totalFreshnessFiles) * 100;
                    if (pct === 0) return null;
                    return (
                      <div
                        key={seg.key}
                        className="h-full"
                        style={{ width: `${pct}%`, backgroundColor: seg.color }}
                        title={`${seg.key}: ${seg.count} (${Math.round(pct)}%)`}
                      />
                    );
                  })}
                </div>
                <div className="flex items-center gap-2.5 mt-2">
                  {[
                    { label: "Fresh", count: age_distribution.fresh, color: t.green },
                    { label: "Aging", count: age_distribution.aging, color: t.amber },
                    { label: "Stale", count: age_distribution.stale, color: t.red },
                    { label: "Abandoned", count: age_distribution.abandoned, color: "#dc2626" },
                  ].map((seg) => (
                    <div key={seg.label} className="flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: seg.color }} />
                      <span className="text-[9px] font-mono text-mc-text-3">
                        {seg.label} <span className="font-bold">{seg.count}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Dependencies — full width */}
        <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-mc-border-0">
            <span className="text-mc-amber">{Icons.folder({ size: 12 })}</span>
            <span className="text-xs font-semibold text-mc-text-0 flex-1">Dependencies</span>
            <span className="text-[10px] font-mono text-mc-text-3">
              {report.dependencies.length} ecosystems
            </span>
          </div>
          <div className="p-4">
            {report.dependencies.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">
                No dependency data
              </div>
            ) : (
              <div className="flex items-center gap-4">
                {totalVulns > 0 && (
                  <div className="flex items-center gap-2 bg-mc-red-muted border border-mc-red-border rounded-lg px-3 py-2">
                    <span className="text-mc-red">{Icons.alert({ size: 12 })}</span>
                    <div>
                      <span className="text-sm font-extrabold font-mono text-mc-red">{totalVulns}</span>
                      <span className="text-[10px] text-mc-text-3 font-mono ml-1">vulnerabilities</span>
                    </div>
                  </div>
                )}
                {totalOutdated > 0 && (
                  <div className="flex items-center gap-2 bg-mc-amber-muted border border-mc-amber-border rounded-lg px-3 py-2">
                    <span className="text-mc-amber">{Icons.refresh({ size: 12 })}</span>
                    <div>
                      <span className="text-sm font-extrabold font-mono text-mc-amber">{totalOutdated}</span>
                      <span className="text-[10px] text-mc-text-3 font-mono ml-1">outdated</span>
                    </div>
                  </div>
                )}
                {totalVulns === 0 && totalOutdated === 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-mc-green">{Icons.check({ size: 12 })}</span>
                    <span className="text-xs text-mc-text-2 font-mono">All dependencies healthy</span>
                  </div>
                )}
                {/* Per-ecosystem badges */}
                <div className="flex items-center gap-1.5 flex-wrap ml-auto">
                  {report.dependencies.map((eco) => (
                    <span
                      key={eco.ecosystem}
                      className="mc-tag bg-mc-surface-2 text-mc-text-3 border border-mc-border-1 text-[9px]"
                    >
                      {eco.ecosystem}
                      <span className="font-bold ml-1">
                        {eco.outdated.length + eco.vulnerabilities.length}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error banner if scan had partial failures */}
      {error && (
        <div className="bg-mc-red-muted border border-mc-red-border rounded-lg px-4 py-2.5 text-xs text-mc-red font-mono">
          {error}
        </div>
      )}
    </div>
  );
}
