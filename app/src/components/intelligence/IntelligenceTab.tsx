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

const DIM_CONFIG: Record<string, { label: string; icon: string; emoji: string; color: string }> = {
  hardcoded: { label: "Hardcoded", icon: "lock", emoji: "\u{1F512}", color: t.red },
  dependency: { label: "Dependencies", icon: "folder", emoji: "\u{1F4E6}", color: t.amber },
  integration: { label: "Integrations", icon: "bolt", emoji: "\u26A1", color: t.cyan },
  freshness: { label: "Freshness", icon: "refresh", emoji: "\u{1F504}", color: t.green },
  feature: { label: "Features", icon: "check", emoji: "\u{1F9E9}", color: t.accent },
};

const SEV_COLOR: Record<string, string> = {
  critical: t.red, high: t.red, warning: t.amber, info: t.text3,
};
const SEV_BG: Record<string, string> = {
  critical: t.redMuted, high: t.redMuted, warning: t.amberMuted, info: "transparent",
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
  issueCount: number;
  dims: string[];
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
        issueCount: findings.length,
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
  const hcCrit = report.hardcoded.findings.filter(f => f.severity === "critical").length;
  const hcWarn = report.hardcoded.findings.filter(f => f.severity === "warning").length;
  const hcScore = Math.max(0, 100 - hcCrit * 10 - hcWarn * 2);
  let depPenalty = 0; let depCrit = 0; let depWarn = 0; let depCount = 0;
  for (const eco of report.dependencies) {
    for (const v of eco.vulnerabilities) {
      depCount++;
      if (v.severity === "critical") { depCrit++; depPenalty += 15; } else { depWarn++; depPenalty += 3; }
    }
    for (const d of eco.outdated) {
      depCount++;
      if (d.update_severity === "major") { depWarn++; depPenalty += 5; } else if (d.update_severity === "minor") depPenalty += 1;
    }
  }
  const depScore = Math.max(0, 100 - depPenalty);
  const totalInt = report.integrations.integrations.length;
  const intScore = totalInt > 0 ? Math.min(100, 50 + totalInt * 5) : 50;
  const freshScore = report.freshness.freshness_score;
  const featScore = report.features.total_features > 0 ? Math.min(100, 50 + report.features.total_features * 2) : 50;
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

const scoreColor = (s: number) => s >= 85 ? t.green : s >= 60 ? t.amber : t.red;
const typeColor = (ty: string) => ty === "ROUTE" ? t.cyan : ty === "API" ? t.red : t.green;

// ── Score Ring SVG ───────────────────────────────────────────────────

function ScoreRing({ score, size = 72 }: { score: number; size?: number }) {
  const strokeWidth = 5;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - score / 100);
  const color = scoreColor(score);
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
          style={{ filter: `drop-shadow(0 0 6px ${color}40)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-extrabold font-mono leading-none text-2xl" style={{ color }}>{grade}</span>
      </div>
    </div>
  );
}

// ── Tag ──────────────────────────────────────────────────────────────

function Tag({ children, color: c = t.text3, bg: b = t.surface2, className = "" }: { children: React.ReactNode; color?: string; bg?: string; className?: string }) {
  return (
    <span
      className={`inline-block whitespace-nowrap font-mono font-semibold uppercase rounded text-[10px] tracking-wide px-[7px] py-[2px] ${className}`}
      style={{ background: b, color: c }}
    >
      {children}
    </span>
  );
}

// ── Props ────────────────────────────────────────────────────────────

interface IntelligenceTabProps {
  onFix?: (source: string, description: string) => void;
  onNavigateToProductMap?: () => void;
}

// ── Main Component ───────────────────────────────────────────────────

export default function IntelligenceTab({ onFix, onNavigateToProductMap }: IntelligenceTabProps) {
  const projectPath = useProjectManager((s) => s.currentProject?.path) ?? "";

  const [report, setReport] = useState<IntelligenceReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectPath) return;
    const cached = getCachedReport(projectPath);
    if (cached) { setReport(cached); return; }
    if (!isBackendConnected()) return;
    let cancelled = false;
    const load = async () => {
      setIsLoading(true); setError(null);
      try {
        const summary = await api.getIntelligenceSummary(projectPath);
        if (cancelled) return;
        if (summary) {
          const fullReport = await api.getIntelligence(projectPath);
          if (cancelled) return;
          setReport(fullReport); setCachedReport(projectPath, fullReport);
        }
      } catch { if (!cancelled) setReport(null); }
      finally { if (!cancelled) setIsLoading(false); }
    };
    void load();
    return () => { cancelled = true; };
  }, [projectPath]);

  const handleScan = useCallback(async (force = false) => {
    if (!projectPath || !isBackendConnected()) return;
    setIsLoading(true); setError(null);
    try {
      const result = await api.scanIntelligence(projectPath, force);
      setReport(result); setCachedReport(projectPath, result);
    } catch (err) { setError(err instanceof Error ? err.message : "Scan failed"); }
    finally { setIsLoading(false); }
  }, [projectPath]);

  const dimScores = useMemo(() => report ? getDimScores(report) : [], [report]);
  const heatEntries = useMemo(() => report ? computeHeatmap(report) : [], [report]);
  const hardcodedByType = useMemo(() => report ? groupHardcodedByType(report.hardcoded.findings) : [], [report]);

  const serviceTypeMap = useMemo(() => {
    if (!report) return new Map<string, string>();
    const counts = new Map<string, Map<string, number>>();
    for (const pt of report.integrations.integrations) {
      if (!counts.has(pt.service_name)) counts.set(pt.service_name, new Map());
      const label = pt.integration_type === "external_api" ? "API"
        : pt.integration_type === "internal_route" ? "ROUTE"
        : pt.integration_type === "sdk_import" ? "SDK" : "DB";
      const m = counts.get(pt.service_name)!;
      m.set(label, (m.get(label) || 0) + 1);
    }
    const result = new Map<string, string>();
    for (const [svc, types] of counts) {
      result.set(svc, [...types.entries()].sort((a, b) => b[1] - a[1])[0][0]);
    }
    return result;
  }, [report]);

  // Integration type totals for stacked bar
  const integrationTypeTotals = useMemo(() => {
    if (!report) return [];
    const totals = new Map<string, number>();
    for (const pt of report.integrations.integrations) {
      const label = pt.integration_type === "external_api" ? "API"
        : pt.integration_type === "internal_route" ? "ROUTE"
        : pt.integration_type === "sdk_import" ? "SDK" : "DB";
      totals.set(label, (totals.get(label) || 0) + 1);
    }
    return [...totals.entries()].map(([label, count]) => ({ label, count, color: typeColor(label) }));
  }, [report]);

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

  const handleOpenFile = useCallback((filePath: string, lineNumber?: number) => {
    if (!projectPath || !isBackendConnected()) return;
    api.openFile(projectPath, filePath, lineNumber).catch(() => {});
  }, [projectPath]);

  const handleGetAnA = () => {
    if (!onFix) return;
    onFix("intelligence", "Analyze which fixes would push the intelligence score above 90 and implement them");
  };

  // Loading skeleton
  if (isLoading && !report) {
    return (
      <div className="mx-auto px-6 py-5">
        <div className="flex flex-col gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  // Empty state
  if (!report && !isLoading && !error) {
    return (
      <div className="mx-auto px-6 py-5">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-text-3">{Icons.search({ size: 32 })}</span>
          <p className="text-sm text-mc-text-2 font-mono text-center">
            No intelligence data. Run a scan to get started.
          </p>
          <Button green onClick={() => handleScan()}>Scan Now</Button>
        </div>
      </div>
    );
  }

  if (error && !report) {
    return (
      <div className="mx-auto px-6 py-5">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-red">{Icons.alert({ size: 32 })}</span>
          <p className="text-sm text-mc-red font-mono text-center">{error}</p>
          <Button onClick={() => handleScan()}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!report) return null;

  const critCount = report.top_issues.filter(i => i.severity === "critical" || i.severity === "high").length;
  const warnCount = report.top_issues.filter(i => i.severity === "warning").length;
  const topHeatFiles = heatEntries.slice(0, 8);
  const maxHeat = Math.max(...topHeatFiles.map(e => e.heat), 1);

  const { age_distribution, freshness_score } = report.freshness;
  const totalFreshnessFiles = report.freshness.files.length;
  const medianAge = totalFreshnessFiles > 0
    ? (() => {
        const sorted = [...report.freshness.files].map(f => f.days_since_modified).sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 === 0 ? Math.round((sorted[mid - 1] + sorted[mid]) / 2) : sorted[mid];
      })()
    : 0;

  const totalVulns = report.dependencies.reduce((s, e) => s + e.vulnerabilities.length, 0);
  const totalOutdated = report.dependencies.reduce((s, e) => s + e.outdated.length, 0);
  const depDimScore = dimScores.find(d => d.category === "dependency")?.score ?? 0;
  const totalHardcodedFindings = report.hardcoded.findings.length;

  return (
    <div className="mx-auto px-6 py-5 flex flex-col gap-5">

      {/* ════════ TIER 1: EXECUTIVE SUMMARY ════════ */}
      <div className="flex gap-3.5">
        {/* Grade Hero */}
        <div
          className="flex-shrink-0 rounded-xl flex flex-col items-center justify-center gap-0.5 w-[130px] p-4 border border-mc-border-0"
          style={{ background: `linear-gradient(135deg, ${t.surface1}, ${t.surface0})` }}
        >
          <ScoreRing score={report.overall_score} size={72} />
          <span className="font-extrabold font-mono text-mc-text-0 text-xl">{report.overall_score}</span>
          <span className="font-mono text-mc-text-3 uppercase text-[8.5px] tracking-[0.12em]">Intelligence</span>
        </div>

        {/* Dimension Cards */}
        <div className="flex-1 grid grid-cols-5 gap-2 min-w-0">
          {dimScores.map((dim) => {
            const cfg = DIM_CONFIG[dim.category];
            if (!cfg) return null;
            const sc = scoreColor(dim.score);
            return (
              <div key={dim.category} className="relative overflow-hidden rounded-[10px] p-3 flex flex-col gap-1.5 bg-mc-surface-1 border border-mc-border-0">
                <div className="absolute top-0 left-0 right-0 h-0.5" style={{ background: sc }} />
                <div className="flex items-center gap-1.5">
                  <span className="text-[13px]">{cfg.emoji}</span>
                  <span className="font-bold text-mc-text-1 text-[10.5px] leading-tight">{cfg.label}</span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="font-extrabold font-mono leading-none text-[22px]" style={{ color: sc }}>{dim.score}</span>
                  {dim.finding_count > 0
                    ? <span className="font-mono text-[10px]" style={{ color: sc }}>{dim.finding_count}</span>
                    : <span className="font-mono text-[10px] text-mc-green">{"\u2713"}</span>
                  }
                </div>
                {dim.top_finding && (
                  <div className="text-mc-text-3 text-[9.5px] leading-snug min-h-[24px]">{dim.top_finding}</div>
                )}
                <div className="flex items-center gap-1.5 mt-auto">
                  <div className="flex-1 h-[3px] rounded-sm bg-mc-surface-3 overflow-hidden">
                    <div className="h-full rounded-sm" style={{ width: `${dim.score}%`, background: sc }} />
                  </div>
                  {onFix && dim.finding_count > 0 && (
                    <button
                      type="button"
                      onClick={() => handleDimFix(dim.category)}
                      className="flex-shrink-0 whitespace-nowrap font-mono font-semibold cursor-pointer px-[7px] py-[2px] rounded bg-mc-accent-muted border border-mc-accent-border text-mc-accent text-[8.5px]"
                    >
                      Fix
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Scan Meta Column */}
        <div className="flex flex-col items-end justify-between flex-shrink-0 font-mono text-mc-text-3 w-[100px] text-[10px]">
          <span>{formatRelativeTime(report.generated_at)}</span>
          <div className="flex flex-col gap-1.5 w-full">
            <button
              type="button"
              onClick={() => handleScan(false)}
              disabled={isLoading}
              className="w-full font-sans font-semibold text-white rounded-md cursor-pointer disabled:opacity-50 px-3.5 py-1.5 text-[11px] bg-mc-green border-none text-center"
            >
              {isLoading ? "Scanning..." : "Scan"}
            </button>
            {onFix && report.overall_score < 90 && (
              <button
                type="button"
                onClick={handleGetAnA}
                className="w-full font-sans font-semibold text-white rounded-md cursor-pointer whitespace-nowrap px-3.5 py-1.5 text-[11px] bg-mc-accent border-none text-center"
              >
                {"\u26A1"} Get an A
              </button>
            )}
          </div>
          <span>{report.total_files_scanned || 0} files</span>
        </div>
      </div>

      {/* ════════ TIER 2: THE STORY ════════ */}
      <div className="grid gap-3.5 grid-cols-[3fr_2fr]">

        {/* Priority Issues */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">Priority Issues</span>
            <div className="flex-1" />
            {critCount > 0 && <span className="font-mono text-[10px] text-mc-red">{critCount} crit</span>}
            {critCount > 0 && warnCount > 0 && <span className="mx-2 bg-mc-border-1 w-px h-2.5" />}
            {warnCount > 0 && <span className="font-mono text-[10px] text-mc-amber">{warnCount} warn</span>}
            {(critCount > 0 || warnCount > 0) && onFix && <span className="mx-2 bg-mc-border-1 w-px h-2.5" />}
            {onFix && report.top_issues.length > 0 && (
              <button
                type="button"
                onClick={handleFixAll}
                className="font-mono font-semibold cursor-pointer px-2.5 py-[3px] rounded-[5px] bg-mc-accent-muted border border-mc-accent-border text-mc-accent text-[9px]"
              >
                Fix All
              </button>
            )}
          </div>
          <div className="flex flex-col max-h-[400px] overflow-y-auto">
            {report.top_issues.length === 0 ? (
              <div className="p-6 text-center text-xs text-mc-text-3 font-mono">No priority issues found</div>
            ) : (
              report.top_issues.map((issue, idx) => {
                const isCrit = issue.severity === "critical" || issue.severity === "high";
                const sevKey = issue.severity === "high" ? "critical" : issue.severity;
                return (
                  <div
                    key={idx}
                    className={`flex items-center gap-2 px-4 py-2 cursor-pointer hover:opacity-90 ${idx > 0 ? "border-t border-mc-border-0" : ""} ${isCrit ? "bg-mc-red-muted" : ""}`}
                    onClick={() => { if (issue.file_path) handleOpenFile(issue.file_path, issue.line_number ?? undefined); }}
                  >
                    <Tag color={SEV_COLOR[sevKey] || t.text3} bg={SEV_BG[sevKey] || "transparent"} className="flex-shrink-0" >
                      {issue.severity === "critical" ? "CRIT" : issue.severity === "high" ? "HIGH" : issue.severity === "warning" ? "WARN" : "INFO"}
                    </Tag>
                    <span
                      className={`flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[11px] ${isCrit ? "text-mc-text-0 font-semibold" : "text-mc-text-1 font-normal"}`}
                    >
                      {truncate(issue.issue, 80)}
                    </span>
                    {issue.file_path && (
                      <span className="flex-shrink-0 font-mono text-mc-text-3 overflow-hidden text-ellipsis whitespace-nowrap text-[9px] max-w-[130px]">
                        {issue.file_path}{issue.line_number ? `:${issue.line_number}` : ""}
                      </span>
                    )}
                    {issue.issue_type && (
                      <Tag color={t.text3} bg={t.surface3} className="flex-shrink-0">{issue.issue_type}</Tag>
                    )}
                    {onFix && issue.severity !== "info" && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleIssueFix(issue); }}
                        className="flex-shrink-0 font-mono font-semibold cursor-pointer px-[7px] py-[2px] rounded bg-mc-accent-muted border border-mc-accent-border text-mc-accent text-[8px]"
                      >
                        Fix
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Debt Heatmap */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">Debt Heatmap</span>
            <div className="flex-1" />
            <span className="font-mono text-mc-text-3 text-[10px]">top {topHeatFiles.length}</span>
          </div>
          {/* Treemap blocks */}
          {heatEntries.length > 0 && (
            <div className="px-3 pt-2.5 pb-1.5 flex flex-wrap gap-[3px]">
              {heatEntries.slice(0, 12).map((entry) => {
                const normalized = Math.min(entry.heat / maxHeat, 1);
                const hc = entry.heat >= 70 ? t.red : entry.heat >= 40 ? t.amber : entry.heat >= 10 ? t.cyan : t.surface3;
                const w = Math.max(36, Math.round(normalized * 70 + 30));
                const h = Math.max(28, Math.round(normalized * 40 + 20));
                const name = entry.filePath.split("/").pop() || "";
                return (
                  <div
                    key={entry.filePath}
                    className="rounded flex items-center justify-center font-mono font-semibold overflow-hidden cursor-pointer text-[7.5px] px-[2px]"
                    style={{ width: w, height: h, background: `${hc}15`, border: `1px solid ${hc}30`, color: hc }}
                    title={`${entry.filePath}\n${entry.issueCount} issues`}
                    onClick={() => handleOpenFile(entry.filePath)}
                  >
                    {entry.issueCount > 0 ? name : ""}
                  </div>
                );
              })}
            </div>
          )}
          {/* Hot files list */}
          <div className="px-3 pb-2.5">
            {topHeatFiles.filter(f => f.issueCount > 0).map((entry, i) => {
              const hc = entry.heat >= 70 ? t.red : entry.heat >= 40 ? t.amber : t.text3;
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 py-[3px] px-1 cursor-pointer hover:opacity-80"
                  onClick={() => handleOpenFile(entry.filePath)}
                >
                  <div className="flex-shrink-0 h-1 rounded-sm bg-mc-surface-3 overflow-hidden w-9">
                    <div className="h-full rounded-sm" style={{ width: `${(entry.heat / maxHeat) * 100}%`, background: hc }} />
                  </div>
                  <span className="font-mono text-mc-text-2 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[10px]">
                    {entry.filePath}
                  </span>
                  <span className="font-mono font-semibold text-[10px] w-3.5 text-right" style={{ color: hc }}>
                    {entry.issueCount}
                  </span>
                  <div className="flex gap-0.5">
                    {entry.dims.map((dm) => (
                      <span key={dm} className="rounded-full w-1 h-1" style={{ background: DIM_CONFIG[dm]?.color || t.text3 }} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ════════ TIER 3: DEEP DIVES (2x2 + full-width) ════════ */}
      <div className="grid grid-cols-2 gap-3.5">

        {/* Hardcoded by Type */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">
              {DIM_CONFIG.hardcoded.emoji} Hardcoded — by type
            </span>
            <div className="flex-1" />
            <Tag color={scoreColor(dimScores.find(d => d.category === "hardcoded")?.score ?? 0)}>
              {totalHardcodedFindings} total
            </Tag>
          </div>
          <div className="px-3.5 py-2.5">
            {hardcodedByType.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">No hardcoded findings</div>
            ) : (
              hardcodedByType.map((group, i) => {
                const pct = Math.round((group.count / Math.max(totalHardcodedFindings, 1)) * 100);
                const c = SEV_COLOR[group.sev] || t.text3;
                const bg = SEV_BG[group.sev] || "transparent";
                return (
                  <div key={group.type} className={`flex items-center gap-2 py-[5px] ${i > 0 ? "border-t border-mc-border-0" : ""}`}>
                    <Tag color={c} bg={bg} className="flex-shrink-0" >{group.count}</Tag>
                    <span className="font-mono text-mc-text-1 flex-shrink-0 text-[10.5px] w-[100px]">{group.type}</span>
                    <div className="flex-1 h-1.5 rounded-sm bg-mc-surface-3 overflow-hidden">
                      <div className="h-full rounded-sm" style={{ width: `${pct}%`, background: `${c}60` }} />
                    </div>
                    <span className="font-mono text-mc-text-3 overflow-hidden text-ellipsis whitespace-nowrap text-[9px] max-w-[130px]">
                      {truncate(group.example, 30)}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Integrations */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">
              {DIM_CONFIG.integration.emoji} Integrations
            </span>
            <div className="flex-1" />
            <span className="font-mono text-mc-text-3 text-[10px]">{report.integrations.services_detected.length} services</span>
          </div>
          <div className="p-3">
            {report.integrations.services_detected.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">No integrations detected</div>
            ) : (
              <div className="grid grid-cols-3 gap-1.5 mb-3">
                {report.integrations.services_detected.slice(0, 9).map((svc) => {
                  const tp = serviceTypeMap.get(svc.service_name) || "API";
                  const tc = typeColor(tp);
                  return (
                    <div
                      key={svc.service_name}
                      className="rounded-md px-2.5 py-2 cursor-pointer hover:opacity-80 bg-mc-surface-2 border border-mc-border-0"
                      onClick={() => {
                        const pts = report.integrations.integrations.filter(i => i.service_name === svc.service_name);
                        if (pts.length > 0) handleOpenFile(pts[0].file_path, pts[0].line_number);
                      }}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="font-bold text-mc-text-0 text-xs">{svc.service_name}</span>
                        <span className="font-mono text-mc-text-3 text-[10px]">{svc.count}</span>
                      </div>
                      <Tag color={tc} bg={`${tc}18`}>{tp}</Tag>
                    </div>
                  );
                })}
              </div>
            )}
            {/* Type distribution stacked bar + legend */}
            {integrationTypeTotals.length > 0 && (
              <>
                <div className="flex h-1.5 rounded-sm overflow-hidden gap-px">
                  {integrationTypeTotals.map(({ label, count, color: c }) => (
                    <div key={label} className="h-full rounded-sm" style={{ flex: count, background: `${c}50` }} />
                  ))}
                </div>
                <div className="flex gap-3 mt-1">
                  {integrationTypeTotals.map(({ label, count, color: c }) => (
                    <span key={label} className="flex items-center gap-1 font-mono text-mc-text-3 text-[9px]">
                      <span className="rounded-full w-[5px] h-[5px]" style={{ background: c }} />
                      {label} {count}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Code Freshness */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">
              {DIM_CONFIG.freshness.emoji} Code Freshness
            </span>
            <div className="flex-1" />
            <Tag color={scoreColor(freshness_score)}>{totalFreshnessFiles} files {"\u00B7"} {Math.round(freshness_score)}%</Tag>
          </div>
          <div className="p-4">
            <div className="flex mb-2.5">
              {[
                { v: totalFreshnessFiles, l: "Files", c: t.text0 },
                { v: report.freshness.stale_files.length, l: "Stale", c: report.freshness.stale_files.length > 0 ? t.amber : t.green },
                { v: report.freshness.abandoned_files.length, l: "Abandoned", c: report.freshness.abandoned_files.length > 0 ? t.red : t.green },
                { v: `${medianAge}d`, l: "Median", c: t.text0 },
              ].map((s, i) => (
                <div key={i} className={`flex-1 text-center ${i < 3 ? "border-r border-mc-border-0" : ""}`}>
                  <div className="font-extrabold font-mono text-lg" style={{ color: s.c }}>{s.v}</div>
                  <div className="font-mono text-mc-text-3 uppercase mt-0.5 text-[8.5px]">{s.l}</div>
                </div>
              ))}
            </div>
            <div className="h-2 rounded bg-mc-surface-3 overflow-hidden">
              {totalFreshnessFiles > 0 && (
                <div className="h-full flex">
                  {[
                    { count: age_distribution.fresh, color: t.green },
                    { count: age_distribution.aging, color: t.amber },
                    { count: age_distribution.stale, color: t.red },
                    { count: age_distribution.abandoned, color: "#dc2626" },
                  ].map((seg, i) => {
                    const pct = (seg.count / totalFreshnessFiles) * 100;
                    if (pct === 0) return null;
                    return <div key={i} className="h-full rounded-sm" style={{ width: `${pct}%`, background: seg.color }} />;
                  })}
                </div>
              )}
            </div>
            <div className="flex gap-3 mt-1.5">
              {[
                { label: "Fresh", count: age_distribution.fresh, color: t.green },
                { label: "Aging", count: age_distribution.aging, color: t.amber },
                { label: "Stale", count: age_distribution.stale, color: t.red },
              ].map((seg) => (
                <span key={seg.label} className="flex items-center gap-1 font-mono text-mc-text-3 text-[9px]">
                  <span className="rounded-full w-[5px] h-[5px]" style={{ background: seg.color }} />
                  {seg.label} {seg.count}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Feature Map */}
        <div className="rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5 border-b border-mc-border-0">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">
              {DIM_CONFIG.feature.emoji} Feature Map
            </span>
            <div className="flex-1" />
            <Tag color={scoreColor(dimScores.find(d => d.category === "feature")?.score ?? 0)}>
              {report.features.total_features} features
            </Tag>
          </div>
          <div className="p-4">
            {report.features.total_features === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">No features detected</div>
            ) : (
              <>
                {/* By-category bar chart */}
                <div className="flex flex-col gap-1">
                  {Object.entries(report.features.by_category)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 6)
                    .map(([cat, count]) => {
                      const pct = Math.round((count / Math.max(report.features.total_features, 1)) * 100);
                      return (
                        <div key={cat} className="flex items-center gap-2 py-[3px]">
                          <span className="font-mono text-mc-text-2 flex-shrink-0 text-[10px] w-20 text-right">{cat}</span>
                          <div className="flex-1 h-1.5 rounded-sm bg-mc-surface-3 overflow-hidden">
                            <div className="h-full rounded-sm" style={{ width: `${pct}%`, background: `${t.accent}60` }} />
                          </div>
                          <span className="font-mono font-semibold text-mc-text-1 flex-shrink-0 text-[10px] w-5">{count}</span>
                        </div>
                      );
                    })}
                </div>
                {/* Insights row */}
                <div className="flex items-center gap-4 mt-3 pt-3 border-t border-mc-border-0">
                  {report.features.untracked_features.length > 0 && (
                    <span className="flex items-center gap-1.5 font-mono text-[10px]">
                      <span className="text-mc-amber">{report.features.untracked_features.length}</span>
                      <span className="text-mc-text-3">untracked</span>
                    </span>
                  )}
                  {report.features.most_coupled.length > 0 && (
                    <span className="flex items-center gap-1.5 font-mono text-[10px]">
                      <span className="text-mc-text-3">top coupled:</span>
                      <span className="text-mc-text-1">{report.features.most_coupled[0].name}</span>
                      <span className="text-mc-text-3">({report.features.most_coupled[0].import_count})</span>
                    </span>
                  )}
                </div>
                {/* Link to Product Map */}
                {onNavigateToProductMap && (
                  <button
                    type="button"
                    onClick={onNavigateToProductMap}
                    className="mt-3 w-full font-mono font-semibold cursor-pointer text-center rounded-md px-3.5 py-1.5 text-[10px] bg-mc-accent-muted border border-mc-accent-border text-mc-accent"
                  >
                    View Product Map &rarr;
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Dependencies — full width */}
        <div className="col-span-2 rounded-[10px] overflow-hidden bg-mc-surface-1 border border-mc-border-0">
          <div className="flex items-center px-4 py-2.5">
            <span className="font-mono font-bold text-mc-text-3 uppercase text-[10px] tracking-wide">
              {DIM_CONFIG.dependency.emoji} Dependencies
            </span>
            <div className="flex-1" />
            <Tag color={scoreColor(depDimScore)}>{depDimScore}</Tag>
          </div>
          <div className="px-4 pb-3">
            {report.dependencies.length === 0 ? (
              <div className="text-xs text-mc-text-3 font-mono text-center py-4">No dependency data</div>
            ) : (
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <span className={`font-extrabold font-mono text-[22px] ${totalOutdated > 0 ? "text-mc-amber" : "text-mc-green"}`}>{totalOutdated}</span>
                  <span className="text-mc-text-3 text-[11px]">outdated</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`font-extrabold font-mono text-[22px] ${totalVulns > 0 ? "text-mc-red" : "text-mc-green"}`}>{totalVulns}</span>
                  <span className="text-mc-text-3 text-[11px]">vulnerable</span>
                </div>
                {/* Inline specific packages */}
                {(totalVulns > 0 || totalOutdated > 0) && (
                  <>
                    <div className="bg-mc-border-1 w-px h-5" />
                    <div className="flex items-center gap-3 flex-wrap flex-1">
                      {report.dependencies.flatMap((eco) => [
                        ...eco.vulnerabilities.map((v) => (
                          <span key={v.advisory_id} className="text-mc-text-3 text-[11px]">
                            <span className="font-bold text-mc-text-1">{v.package_name}</span> {truncate(v.title, 35)}{" "}
                            <Tag color={SEV_COLOR[v.severity] || t.text3} bg={SEV_BG[v.severity] || t.surface2}>{v.severity}</Tag>
                          </span>
                        )),
                        ...eco.outdated.map((d) => (
                          <span key={`${eco.ecosystem}-${d.name}`} className="text-mc-text-3 text-[11px]">
                            {d.name} {d.current_version} {"\u2192"} {d.latest_version}{" "}
                            <Tag color={d.update_severity === "major" ? t.red : t.amber} bg={d.update_severity === "major" ? t.redMuted : t.amberMuted}>
                              {d.update_severity || "patch"}
                            </Tag>
                          </span>
                        )),
                      ]).slice(0, 4)}
                    </div>
                  </>
                )}
                {totalVulns === 0 && totalOutdated === 0 && (
                  <span className="text-mc-text-3 text-[11px]">All dependencies healthy</span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-mc-red-muted border border-mc-red-border rounded-lg px-4 py-2.5 text-xs text-mc-red font-mono">
          {error}
        </div>
      )}
    </div>
  );
}
