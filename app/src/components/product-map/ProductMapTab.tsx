import { useCallback, useEffect, useState, useRef, useMemo } from "react";
import type { ProductMapResponse, ProductFeature, ActionStep, ReadinessDimension } from "../../types";
import { api, isBackendConnected } from "../../api/backend";
import { useProjectManager } from "../../managers/projectManager";
import { t } from "../../styles/tokens";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";

// ── Utility functions ────────────────────────────────────────────────

function readinessColor(r: number): string {
  if (r >= 80) return t.green;
  if (r >= 50) return t.amber;
  return t.red;
}

function statusColor(status: string): string {
  if (status === "active") return t.green;
  if (status === "planned") return t.cyan;
  if (status === "deprecated") return t.text3;
  return t.text2;
}

const IMPACT_COLOR: Record<string, string> = {
  high: t.red,
  medium: t.amber,
  low: t.text3,
};

function parseDaysAgo(lastTouched: string): number {
  if (!lastTouched) return 30;
  const s = lastTouched.toLowerCase().trim();
  // Match patterns: "2d ago", "3 days ago", "2w ago", "3 weeks ago", "1mo ago", "1 month ago"
  const m = s.match(/^(\d+)\s*(d|day|days|w|week|weeks|mo|month|months)\s*(ago)?$/);
  if (!m) return 30;
  const n = parseInt(m[1], 10);
  const unit = m[2];
  if (unit.startsWith("d")) return n;
  if (unit.startsWith("w")) return n * 7;
  if (unit.startsWith("mo")) return n * 30;
  return 30;
}

interface RankedFeature extends ProductFeature {
  priorityScore: number;
  priorityRank: number;
}

function rankFeatures(features: ProductFeature[]): RankedFeature[] {
  const scored = features.map((f) => {
    const dependedByWeight = 1 + f.dependedBy.length * 0.5;
    const daysSinceTouch = parseDaysAgo(f.lastTouched);
    const stalenessFactor = 1 + daysSinceTouch / 30;
    const priorityScore = Math.round(dependedByWeight * (100 - f.readiness) * stalenessFactor);
    return { ...f, priorityScore, priorityRank: 0 };
  });
  scored.sort((a, b) => b.priorityScore - a.priorityScore);
  scored.forEach((f, i) => { f.priorityRank = i + 1; });
  return scored;
}

function parseEffortSessions(effort: string): number {
  const m = effort.match(/(\d+)/);
  return m ? parseInt(m[1], 10) : 1;
}

// ── Props ────────────────────────────────────────────────────────────

interface ProductMapTabProps {
  onFix?: (source: string, description: string) => void;
}

// ── Main Component ───────────────────────────────────────────────────

export function ProductMapTab({ onFix }: ProductMapTabProps) {
  const projectPath = useProjectManager((s) => s.currentProject?.path) ?? "";

  const [productMap, setProductMap] = useState<ProductMapResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);
  const [scanProgress, setScanProgress] = useState("Claude is analyzing your project...");
  const abortRef = useRef<(() => void) | null>(null);

  // Derived state
  const rankedFeatures = useMemo<RankedFeature[]>(() => {
    if (!productMap) return [];
    return rankFeatures(productMap.features);
  }, [productMap]);

  const priorityQueue = useMemo(
    () => rankedFeatures.filter((f) => f.readiness < 80).slice(0, 4),
    [rankedFeatures],
  );

  const summary = useMemo(() => {
    const totalActions = rankedFeatures.reduce(
      (s, f) => s + (f.actionPlan?.length ?? 0), 0,
    );
    const totalSessions = rankedFeatures.reduce(
      (s, f) => s + (f.actionPlan ?? []).reduce((ss, a) => ss + parseEffortSessions(a.effort), 0), 0,
    );
    const readyCt = rankedFeatures.filter((f) => f.readiness >= 80).length;
    const buildingCt = rankedFeatures.filter((f) => f.readiness >= 50 && f.readiness < 80).length;
    const earlyCt = rankedFeatures.filter((f) => f.readiness < 50).length;
    return { totalActions, totalSessions, readyCt, buildingCt, earlyCt };
  }, [rankedFeatures]);

  // Load cached data on mount
  useEffect(() => {
    if (!projectPath || !isBackendConnected()) return;
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      try {
        const cached = await api.getProductMap(projectPath);
        if (!cancelled) setProductMap(cached);
      } catch {
        // No cached data — user needs to generate
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void load();
    return () => { cancelled = true; };
  }, [projectPath]);

  // Cleanup abort on unmount
  useEffect(() => {
    return () => { abortRef.current?.(); };
  }, []);

  // Generate handler — background job + polling
  const handleGenerate = useCallback(async (force = false) => {
    if (!projectPath || !isBackendConnected()) return;
    setIsScanning(true);
    setError(null);
    setScanProgress(force ? "Running full rescan..." : "Analyzing changes...");

    try {
      const { promise, abort } = api.scanProductMap(
        projectPath,
        (msg) => setScanProgress(msg),
        force,
      );
      abortRef.current = abort;

      const result = await promise;
      setProductMap(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Product map generation failed");
    } finally {
      setIsScanning(false);
      abortRef.current = null;
    }
  }, [projectPath]);

  // Dispatch handlers
  const handleFeatureFix = (feature: ProductFeature) => {
    if (!onFix) return;
    const actions = feature.actionPlan;
    if (actions && actions.length > 0) {
      const plan = actions.map((a, i) => `${i + 1}. ${a.action}`).join("\n");
      onFix("product-map", `Improve "${feature.name}" feature:\n${plan}`);
    } else {
      const gaps = feature.lacks.length > 0
        ? feature.lacks.join(", ")
        : "Improve readiness score";
      onFix("product-map", `Improve "${feature.name}" feature: ${gaps}`);
    }
  };

  const handleFixTop3 = () => {
    if (!onFix || priorityQueue.length === 0) return;
    const top3 = priorityQueue.slice(0, 3);
    const plan = top3.map((f) => {
      const actions = (f.actionPlan ?? []).map((a) => a.action).join("; ");
      return `- ${f.name}: ${actions || f.lacks.join(", ") || "Improve readiness"}`;
    }).join("\n");
    onFix("product-map", `Fix top 3 priority features:\n${plan}`);
  };

  const handleRunAction = (feature: ProductFeature, action: ActionStep) => {
    if (!onFix) return;
    onFix("product-map", `${feature.name}: ${action.action}`);
  };

  const scrollToFeature = (name: string) => {
    setExpandedFeature(name);
    // Defer scroll to after render
    requestAnimationFrame(() => {
      const el = document.getElementById(`feature-${name}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  // Loading state
  if (isLoading && !productMap) {
    return (
      <div className="max-w-[1120px] mx-auto p-6">
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  // Scanning state
  if (isScanning) {
    return (
      <div className="max-w-[1120px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-5">
          <div className="relative flex-shrink-0" style={{ width: 56, height: 56 }}>
            <svg width={56} height={56} viewBox="0 0 56 56" className="animate-spin" style={{ animationDuration: "2s" }}>
              <circle cx={28} cy={28} r={22} fill="none" stroke={t.surface3} strokeWidth={4} />
              <circle
                cx={28} cy={28} r={22} fill="none"
                stroke={t.accent}
                strokeWidth={4}
                strokeDasharray={2 * Math.PI * 22}
                strokeDashoffset={2 * Math.PI * 22 * 0.75}
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-mc-green animate-pulse" />
            <span className="text-xs text-mc-text-1 font-mono">{scanProgress}</span>
          </div>
          <p className="text-[10px] text-mc-text-3 font-mono text-center max-w-xs">
            Claude is reading source code, CLAUDE.md, ROADMAP.md, and git history.
            This typically takes 1-3 minutes.
          </p>
        </div>
      </div>
    );
  }

  // Empty state
  if (!productMap && !isLoading && !isScanning && !error) {
    return (
      <div className="max-w-[1120px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="4" y="8" width="40" height="32" rx="4" stroke={t.text3} strokeWidth="2" />
            <path d="M4 16h40" stroke={t.text3} strokeWidth="2" />
            <rect x="10" y="22" width="12" height="8" rx="2" stroke={t.accent} strokeWidth="1.5" />
            <rect x="26" y="22" width="12" height="8" rx="2" stroke={t.accent} strokeWidth="1.5" />
            <rect x="10" y="33" width="28" height="3" rx="1" stroke={t.text3} strokeWidth="1" opacity="0.4" />
          </svg>
          <p className="text-sm text-mc-text-2 font-mono text-center max-w-xs">
            Product Map uses Claude to analyze your project at the product level —
            features, readiness, gaps, and dependencies.
          </p>
          <Button primary onClick={() => handleGenerate()} disabled={isScanning}>
            Generate Product Map
          </Button>
          <span className="text-[10px] text-mc-text-3 font-mono">
            Takes 1-3 minutes. Uses Claude Code to analyze the project.
          </span>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !productMap) {
    return (
      <div className="max-w-[1120px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-red">{Icons.alert({ size: 32 })}</span>
          <p className="text-sm text-mc-red font-mono text-center max-w-md">{error}</p>
          <Button onClick={() => handleGenerate()}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!productMap) return null;

  const avgReadiness = productMap.avg_readiness;

  return (
    <div className="max-w-[1120px] mx-auto p-6 flex flex-col gap-5">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl p-5 animate-fade-in">
        <div className="flex items-center gap-4">
          {/* Avg readiness ring */}
          <div className="relative flex-shrink-0" style={{ width: 48, height: 48 }}>
            <svg width={48} height={48} viewBox="0 0 48 48" className="-rotate-90">
              <circle cx={24} cy={24} r={20} fill="none" stroke={t.surface3} strokeWidth={4} />
              <circle
                cx={24} cy={24} r={20} fill="none"
                stroke={readinessColor(avgReadiness)}
                strokeWidth={4}
                strokeDasharray={2 * Math.PI * 20}
                strokeDashoffset={2 * Math.PI * 20 * (1 - avgReadiness / 100)}
                strokeLinecap="round"
                className="transition-all duration-500"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span
                className="text-[13px] font-extrabold font-mono"
                style={{ color: readinessColor(avgReadiness) }}
              >
                {avgReadiness}%
              </span>
            </div>
          </div>

          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-widest">
              Product Map
            </div>
            <div className="text-[11px] text-mc-text-2 mt-0.5">
              {rankedFeatures.length} features · {summary.totalActions} actions · ~{summary.totalSessions} sessions to 100%
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold font-mono px-[7px] py-[2px] rounded bg-mc-green-muted text-mc-green">
              {summary.readyCt} ready
            </span>
            <span className="text-[10px] font-semibold font-mono px-[7px] py-[2px] rounded bg-mc-amber-muted text-mc-amber">
              {summary.buildingCt} building
            </span>
            <span className="text-[10px] font-semibold font-mono px-[7px] py-[2px] rounded bg-mc-red-muted text-mc-red">
              {summary.earlyCt} early
            </span>
          </div>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-mc-border-0">
          <span className="text-[10px] text-mc-text-3 font-mono">
            {new Date(productMap.generated_at).toLocaleDateString()}
          </span>
          {productMap.scan_mode && (
            <span className={`text-[10px] font-mono ${productMap.scan_mode === "cached" ? "text-mc-green" : productMap.scan_mode === "delta" ? "text-mc-cyan" : "text-mc-text-3"}`}>
              {productMap.scan_mode === "cached" ? "cached" : productMap.scan_mode === "delta" ? "delta" : "full scan"}
            </span>
          )}
          {productMap.commit_hash && (
            <span className="text-[10px] text-mc-text-3 font-mono" title={productMap.commit_hash}>
              {productMap.commit_hash.slice(0, 7)}
            </span>
          )}
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => handleGenerate(true)}
            disabled={isScanning}
            className="text-[10px] font-mono text-mc-text-3 hover:text-mc-accent transition-colors cursor-pointer disabled:opacity-40"
          >
            Force full rescan
          </button>
          <Button small onClick={() => handleGenerate(false)} disabled={isScanning}>
            {isScanning ? "Analyzing..." : "Regenerate"}
          </Button>
        </div>
      </div>

      {/* ── Priority Queue ─────────────────────────────────────── */}
      {priorityQueue.length > 0 && (
        <div className="animate-fade-in">
          <div className="flex items-center gap-2 mb-2.5">
            <span className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-widest">
              Priority Queue
            </span>
            <span className="text-[10px] text-mc-text-3">
              — what to fix first and why
            </span>
            <div className="flex-1" />
            {onFix && (
              <Button small primary onClick={handleFixTop3}>
                Fix Top 3
              </Button>
            )}
          </div>

          <div
            className="grid gap-2.5"
            style={{ gridTemplateColumns: `repeat(${priorityQueue.length}, 1fr)` }}
          >
            {priorityQueue.map((feat, i) => {
              const fc = readinessColor(feat.readiness);
              const topAction = feat.actionPlan?.[0];
              return (
                <button
                  key={feat.name}
                  type="button"
                  onClick={() => scrollToFeature(feat.name)}
                  className="text-left bg-mc-surface-1 rounded-[10px] overflow-hidden relative cursor-pointer hover:bg-mc-surface-2 transition-colors"
                  style={{ border: `1px solid ${i === 0 ? fc + "30" : "rgba(255,255,255,0.04)"}`, padding: 14 }}
                >
                  {/* Colored top edge */}
                  <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: fc }} />
                  {/* Priority number watermark */}
                  <div
                    className="absolute top-2 right-2.5 font-mono font-black leading-none text-mc-surface-3"
                    style={{ fontSize: 28 }}
                  >
                    #{i + 1}
                  </div>
                  {/* Name + readiness */}
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[13px] font-bold text-mc-text-0">{feat.name}</span>
                    <div className="flex-1" />
                    <span className="text-sm font-mono font-extrabold" style={{ color: fc }}>
                      {feat.readiness}%
                    </span>
                  </div>
                  {/* Why matters excerpt */}
                  {feat.whyMatters && (
                    <div
                      className="text-[10.5px] text-mc-text-2 leading-[1.4] mb-2"
                      style={{
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {feat.whyMatters}
                    </div>
                  )}
                  {/* Top action */}
                  {topAction && (
                    <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-[5px] bg-mc-surface-2">
                      <span
                        className="text-[8px] font-semibold font-mono uppercase px-[5px] py-[1px] rounded"
                        style={{
                          color: IMPACT_COLOR[topAction.impact] ?? t.text3,
                          background: (IMPACT_COLOR[topAction.impact] ?? t.text3) + "15",
                        }}
                      >
                        {topAction.impact}
                      </span>
                      <span className="text-[10px] text-mc-text-1 flex-1 truncate">
                        {topAction.action}
                      </span>
                      <span className="text-[9px] font-mono text-mc-text-3 flex-shrink-0">
                        {topAction.effort}
                      </span>
                    </div>
                  )}
                  {/* Meta row */}
                  <div className="flex items-center gap-2 mt-2">
                    <span
                      className="text-[9px] font-mono"
                      style={{ color: feat.trend > 0 ? t.green : feat.trend < 0 ? t.red : t.text3 }}
                    >
                      {feat.trend > 0 ? "↑" : feat.trend < 0 ? "↓" : "—"}
                      {Math.abs(feat.trend) || ""}
                    </span>
                    <span className="text-[9px] font-mono text-mc-text-3">{feat.lastTouched}</span>
                    <span className="text-[9px] font-mono text-mc-text-3">
                      {feat.momentum?.commits ?? 0} commits
                    </span>
                    <div className="flex-1" />
                    <span className="text-[9px] font-mono text-mc-text-3">
                      {feat.actionPlan?.length ?? 0} actions
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Full Inventory ─────────────────────────────────────── */}
      <div className="animate-fade-in">
        <div className="flex items-center gap-2 mb-2.5">
          <span className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-widest">
            All Features
          </span>
          <span className="text-[10px] text-mc-text-3">— sorted by priority</span>
        </div>

        <div className="flex flex-col gap-1">
          {rankedFeatures.map((feat) => {
            const isExpanded = expandedFeature === feat.name;
            const fc = readinessColor(feat.readiness);
            const trendColor = feat.trend > 0 ? t.green : feat.trend < 0 ? t.red : t.text3;

            return (
              <div
                key={feat.name}
                id={`feature-${feat.name}`}
                className={`rounded-lg overflow-hidden transition-all ${isExpanded ? "bg-mc-surface-1 border-mc-border-2" : "bg-mc-surface-0 border-mc-border-0"}`}
                style={{ border: `1px solid ${isExpanded ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.04)"}` }}
              >
                {/* Collapsed row */}
                <button
                  type="button"
                  onClick={() => setExpandedFeature(isExpanded ? null : feat.name)}
                  className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-left hover:bg-mc-surface-2 transition-colors cursor-pointer"
                >
                  <span className="text-[10px] font-mono text-mc-text-3 w-[18px] text-right flex-shrink-0">
                    #{feat.priorityRank}
                  </span>
                  <span
                    className="text-[10px] text-mc-text-3 flex-shrink-0 transition-transform"
                    style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
                  >
                    ▸
                  </span>
                  <span className="text-[13px] font-bold text-mc-text-0 min-w-[160px] flex-shrink-0 truncate">
                    {feat.name}
                  </span>
                  <span
                    className="text-[8px] font-semibold font-mono uppercase px-[7px] py-[2px] rounded flex-shrink-0"
                    style={{
                      color: statusColor(feat.status),
                      background: statusColor(feat.status) + "15",
                    }}
                  >
                    {feat.status}
                  </span>
                  <span
                    className="text-[10px] font-mono font-bold flex-shrink-0"
                    style={{ color: trendColor }}
                  >
                    {feat.trend > 0 ? "↑" : feat.trend < 0 ? "↓" : "—"}
                    {Math.abs(feat.trend) || ""}
                  </span>
                  <span className="text-[9.5px] font-mono text-mc-text-3 flex-shrink-0">
                    {feat.lastTouched}
                  </span>
                  <div className="flex-1" />
                  {feat.dependedBy.length > 0 && (
                    <span className="text-[9px] font-mono text-mc-red flex-shrink-0" title="Features that depend on this">
                      {feat.dependedBy.length} dep
                    </span>
                  )}
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <div className="w-12 h-1 rounded-full bg-mc-surface-3 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{ width: `${feat.readiness}%`, backgroundColor: fc }}
                      />
                    </div>
                    <span
                      className="text-[11px] font-mono font-bold w-7 text-right"
                      style={{ color: fc }}
                    >
                      {feat.readiness}%
                    </span>
                  </div>
                  {onFix && feat.readiness < 80 && (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => { e.stopPropagation(); handleFeatureFix(feat); }}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); handleFeatureFix(feat); } }}
                      className="text-[8.5px] font-semibold font-mono px-[7px] py-[2px] rounded bg-mc-accent-muted border border-mc-accent-border text-mc-accent cursor-pointer flex-shrink-0 hover:opacity-80"
                    >
                      Fix
                    </span>
                  )}
                </button>

                {/* Expanded PM analysis */}
                {isExpanded && (
                  <div className="px-3.5 pb-4 animate-fade-in" style={{ paddingLeft: 48 }}>
                    <div className="flex flex-col gap-3">
                      {/* 1. Description */}
                      <div className="text-xs text-mc-text-1 leading-relaxed">
                        {feat.desc}
                      </div>

                      {/* 2. Why This Matters */}
                      {feat.whyMatters && (
                        <div
                          className="px-3 py-2.5 rounded-md bg-mc-cyan-muted"
                          style={{ borderLeft: `3px solid ${t.cyan}` }}
                        >
                          <div className="text-[9px] font-mono font-semibold text-mc-cyan uppercase mb-1">
                            Why this matters
                          </div>
                          <div className="text-[11px] text-mc-text-1 leading-relaxed">
                            {feat.whyMatters}
                          </div>
                        </div>
                      )}

                      {/* 3. Risk If Ignored */}
                      {feat.riskIfIgnored && (
                        <div
                          className="px-3 py-2.5 rounded-md bg-mc-red-muted"
                          style={{ borderLeft: `3px solid ${t.red}` }}
                        >
                          <div className="text-[9px] font-mono font-semibold text-mc-red uppercase mb-1">
                            Risk if ignored
                          </div>
                          <div className="text-[11px] text-mc-text-1 leading-relaxed">
                            {feat.riskIfIgnored}
                          </div>
                        </div>
                      )}

                      {/* 4. Action Plan */}
                      {feat.actionPlan && feat.actionPlan.length > 0 && (
                        <div className="px-3 py-2.5 rounded-md bg-mc-surface-2 border border-mc-border-1">
                          <div className="flex items-center mb-1.5">
                            <span className="text-[9px] font-mono font-semibold text-mc-accent uppercase">
                              Action Plan
                            </span>
                            <div className="flex-1" />
                            <span className="text-[9px] font-mono text-mc-text-3">
                              {feat.actionPlan.length} actions · ~{feat.actionPlan.reduce((s, a) => s + parseEffortSessions(a.effort), 0)} sessions
                            </span>
                          </div>
                          {feat.actionPlan.map((ap, ai) => (
                            <div
                              key={ai}
                              className="flex items-center gap-2 py-1.5"
                              style={{ borderTop: ai > 0 ? `1px solid rgba(255,255,255,0.04)` : "none" }}
                            >
                              <span className="text-[10px] font-mono text-mc-text-3 w-3.5 text-right flex-shrink-0">
                                {ai + 1}.
                              </span>
                              <span
                                className="text-[8px] font-semibold font-mono uppercase px-[5px] py-[1px] rounded flex-shrink-0"
                                style={{
                                  color: IMPACT_COLOR[ap.impact] ?? t.text3,
                                  background: (IMPACT_COLOR[ap.impact] ?? t.text3) + "15",
                                }}
                              >
                                {ap.impact}
                              </span>
                              <span className="text-[11px] text-mc-text-1 flex-1">
                                {ap.action}
                              </span>
                              <span className="text-[9px] font-mono text-mc-text-3 flex-shrink-0">
                                {ap.effort}
                              </span>
                              {onFix && (
                                <span
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => { e.stopPropagation(); handleRunAction(feat, ap); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); handleRunAction(feat, ap); } }}
                                  className="text-[8px] font-semibold font-mono px-[7px] py-[2px] rounded bg-mc-accent-muted border border-mc-accent-border text-mc-accent cursor-pointer flex-shrink-0 hover:opacity-80"
                                >
                                  Run
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* 5. Stats + Last Session */}
                      <div className="flex items-center gap-3.5 flex-wrap">
                        {[
                          { label: "Files", value: String(feat.files), color: t.text0 },
                          { label: "Tests", value: String(feat.tests), color: feat.tests === 0 ? t.red : feat.tests < 3 ? t.amber : t.green },
                          { label: "Momentum", value: String(feat.momentum?.commits ?? 0), color: (feat.momentum?.commits ?? 0) > 3 ? t.green : (feat.momentum?.commits ?? 0) > 0 ? t.text1 : t.red, suffix: ` commits ${feat.momentum?.period ?? ""}` },
                        ].map((s, i) => (
                          <div key={i} className="flex items-center gap-1">
                            <span className="text-[9px] font-mono text-mc-text-3 uppercase">{s.label}</span>
                            <span className="text-xs font-mono font-bold" style={{ color: s.color }}>{s.value}</span>
                            {s.suffix && <span className="text-[9px] text-mc-text-3">{s.suffix}</span>}
                          </div>
                        ))}
                      </div>

                      {feat.lastSession && (
                        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-mc-surface-0 border border-mc-border-0">
                          <span className="text-[9px] font-mono text-mc-text-3 uppercase flex-shrink-0">Last session</span>
                          <span className="text-[11px] text-mc-text-1 italic">"{feat.lastSession}"</span>
                        </div>
                      )}

                      {/* 6. Readiness Dot Grid */}
                      {feat.readinessDetail.length > 0 && (
                        <div className="flex gap-3.5 flex-wrap">
                          {feat.readinessDetail.map((rd: ReadinessDimension, i: number) => {
                            const haveNum = typeof rd.have === "number" ? rd.have : null;
                            const needNum = typeof rd.need === "number" ? rd.need : null;

                            if (haveNum !== null && needNum !== null && needNum > 0) {
                              // Numeric mode: render dots
                              const dotColor = haveNum >= needNum ? t.green : haveNum > 0 ? t.amber : t.red;
                              return (
                                <div key={i} className="flex items-center gap-1">
                                  <span className="text-[9px] font-mono text-mc-text-3 w-[72px] text-right">
                                    {rd.dim}
                                  </span>
                                  <div className="flex gap-[2px]">
                                    {Array.from({ length: haveNum }).map((_, j) => (
                                      <span
                                        key={`f${j}`}
                                        className="w-[7px] h-[7px] rounded-full"
                                        style={{ background: dotColor }}
                                      />
                                    ))}
                                    {Array.from({ length: Math.max(0, needNum - haveNum) }).map((_, j) => (
                                      <span
                                        key={`e${j}`}
                                        className="w-[7px] h-[7px] rounded-full bg-mc-surface-3 border border-mc-border-1"
                                      />
                                    ))}
                                  </div>
                                  <span className="text-[9px] font-mono" style={{ color: dotColor }}>
                                    {haveNum}/{needNum}
                                  </span>
                                </div>
                              );
                            }

                            // String (legacy) mode: show have → need
                            return (
                              <div key={i} className="flex items-start gap-2">
                                <span className="text-[10px] font-mono text-mc-text-2 w-20 flex-shrink-0">
                                  {rd.dim}
                                </span>
                                <span className="text-[10px] font-mono text-mc-green flex-shrink-0">
                                  {String(rd.have)}
                                </span>
                                <span className="text-[10px] text-mc-text-3">→</span>
                                <span className="text-[10px] font-mono text-mc-amber">
                                  {String(rd.need)}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* 7. Dependencies */}
                      {(feat.integrations.length > 0 || feat.dependsOn.length > 0 || feat.dependedBy.length > 0) && (
                        <div className="flex gap-5 flex-wrap">
                          {feat.integrations.length > 0 && (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-[9px] font-mono text-mc-text-3 uppercase">Calls</span>
                              {feat.integrations.map((intg, i) => (
                                <span
                                  key={i}
                                  className="text-[9px] font-semibold font-mono uppercase px-[7px] py-[2px] rounded"
                                  style={{ color: t.cyan, background: t.cyan + "12" }}
                                >
                                  {intg}
                                </span>
                              ))}
                            </div>
                          )}
                          {feat.dependsOn.length > 0 && (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-[9px] font-mono text-mc-text-3 uppercase">Depends on</span>
                              {feat.dependsOn.map((dep, i) => (
                                <span
                                  key={i}
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => { e.stopPropagation(); scrollToFeature(dep); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); scrollToFeature(dep); } }}
                                  className="text-[9px] font-semibold font-mono uppercase px-[7px] py-[2px] rounded bg-mc-surface-3 text-mc-text-2 cursor-pointer hover:text-mc-text-0"
                                >
                                  {dep}
                                </span>
                              ))}
                            </div>
                          )}
                          {feat.dependedBy.length > 0 && (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-[9px] font-mono text-mc-red uppercase">Depended by</span>
                              {feat.dependedBy.map((dep, i) => (
                                <span
                                  key={i}
                                  role="button"
                                  tabIndex={0}
                                  onClick={(e) => { e.stopPropagation(); scrollToFeature(dep); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); scrollToFeature(dep); } }}
                                  className="text-[9px] font-semibold font-mono uppercase px-[7px] py-[2px] rounded bg-mc-red-muted text-mc-red cursor-pointer hover:opacity-80"
                                >
                                  {dep}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
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
