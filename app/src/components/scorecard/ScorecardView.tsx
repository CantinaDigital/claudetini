/**
 * Readiness Scorecard View
 *
 * - Progressive lazy-loading: shows scorecard layout immediately, reveals
 *   checks one by one as they "grade" (staggered animation)
 * - Design tokens via Tailwind mc-* namespace
 * - Three-tier layout: Essential, Recommended, Optional
 * - Selective bootstrap checkboxes on failed items
 * - Dismiss per item with score recomputation
 * - "Needs attention" callout
 * - `why` field on failed items
 * - Remediation hint on all failed items
 * - Dynamic bootstrap count on button
 * - "Skip for Now" / "Continue to Dashboard" adaptive action
 * - Correct score thresholds (green>=85, amber>=60, red<60)
 */

import { useEffect, useState, useMemo, useRef } from "react";
import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import { Tag } from "../ui/Tag";
import { ReadinessRing } from "./ReadinessRing";
import { api } from "../../api/backend";
import { useProjectManager } from "../../managers/projectManager";
import type { ReadinessCheck, ReadinessReport } from "../../types";

interface ScorecardViewProps {
  projectPath: string;
  onBootstrap: () => void;
  onSkip: () => void;
  onBack?: () => void;
  onRefresh?: () => void;
}

// Tier grouping: severity -> tier
type TierKey = "essential" | "recommended" | "optional";

interface TierGroup {
  key: TierKey;
  label: string;
  description: string;
  items: ReadinessCheck[];
  borderColor: string;
  tagColor: string;
  tagBg: string;
}

const SEVERITY_TO_TIER: Record<string, TierKey> = {
  critical: "essential",
  important: "recommended",
  nice_to_have: "optional",
};

const TIER_META: Record<TierKey, { label: string; description: string; borderColor: string; tagColor: string; tagBg: string }> = {
  essential: {
    label: "Essential",
    description: "Required for Claude Code to work effectively",
    borderColor: t.redBorder,
    tagColor: t.red,
    tagBg: t.redMuted,
  },
  recommended: {
    label: "Recommended",
    description: "Strongly recommended for best results",
    borderColor: t.amberBorder,
    tagColor: t.amber,
    tagBg: t.amberMuted,
  },
  optional: {
    label: "Optional",
    description: "Nice to have but not required",
    borderColor: t.border1,
    tagColor: t.text3,
    tagBg: t.surface3,
  },
};

const CATEGORY_NAMES: Record<string, string> = {
  version_control: "Version Control",
  documentation: "Documentation",
  planning: "Planning",
  project_structure: "Project Structure",
  legal: "Legal",
  testing: "Testing",
  automation: "Automation",
  security: "Security",
};

// Stagger delay per check (ms) for the reveal animation
const REVEAL_STAGGER_MS = 120;

export function ScorecardView({
  projectPath,
  onBootstrap,
  onSkip,
  onBack,
  onRefresh,
}: ScorecardViewProps) {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [scanning, setScanning] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [bootstrapSel, setBootstrapSel] = useState<Set<string>>(new Set());
  // Progressive reveal: how many checks have been "graded" visually
  const [revealedCount, setRevealedCount] = useState(0);
  const revealTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Delay before showing the final score (let ring animate after checks reveal)
  const [showFinalScore, setShowFinalScore] = useState(false);

  const fetchReadiness = async () => {
    setScanning(true);
    setError(null);
    setRevealedCount(0);
    setShowFinalScore(false);
    if (revealTimerRef.current) clearInterval(revealTimerRef.current);
    try {
      const data = await api.scanReadiness(projectPath);
      setReport(data);
      // Store in project manager for overview tab to use
      useProjectManager.setState({
        readinessScore: data.score,
        readinessReport: data,
      });
      // Pre-check all failed items for bootstrap
      const failedKeys = new Set(data.checks.filter((c) => !c.passed).map((c) => c.name));
      setBootstrapSel(failedKeys);
      setDismissed(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    fetchReadiness();
    return () => {
      if (revealTimerRef.current) clearInterval(revealTimerRef.current);
    };
  }, [projectPath]);

  // Start progressive reveal when report arrives
  useEffect(() => {
    if (!report || scanning) return;
    const total = report.checks.length;
    if (total === 0) {
      setShowFinalScore(true);
      return;
    }
    let count = 0;
    revealTimerRef.current = setInterval(() => {
      count++;
      setRevealedCount(count);
      if (count >= total) {
        if (revealTimerRef.current) clearInterval(revealTimerRef.current);
        revealTimerRef.current = null;
        // Show final score after a brief pause
        setTimeout(() => setShowFinalScore(true), 300);
      }
    }, REVEAL_STAGGER_MS);
    return () => {
      if (revealTimerRef.current) {
        clearInterval(revealTimerRef.current);
        revealTimerRef.current = null;
      }
    };
  }, [report, scanning]);

  const handleRefresh = () => {
    fetchReadiness();
    onRefresh?.();
  };

  // Set of revealed check names (for progressive display)
  const revealedNames = useMemo(() => {
    if (!report) return new Set<string>();
    return new Set(report.checks.slice(0, revealedCount).map((c) => c.name));
  }, [report, revealedCount]);

  const allRevealed = report ? revealedCount >= report.checks.length : false;

  // Derived data with dismiss support (only considers revealed checks for score)
  const { passed, total, failed, selectedForBootstrap, score } = useMemo(() => {
    if (!report) return { passed: 0, total: 0, failed: [] as ReadinessCheck[], selectedForBootstrap: [] as ReadinessCheck[], score: 0 };
    const active = report.checks.filter((c) => !dismissed.has(c.name));
    // For score computation during reveal, only count revealed checks
    const revealedActive = active.filter((c) => revealedNames.has(c.name));
    const pass = revealedActive.filter((c) => c.passed);
    const fail = active.filter((c) => !c.passed);
    const revealedFail = revealedActive.filter((c) => !c.passed);
    const selBoot = fail.filter((c) => bootstrapSel.has(c.name));
    // Progressive score: only penalize revealed failures
    const computedScore = Math.max(
      0,
      Math.round(
        100 - revealedFail.reduce((s, c) => s + (c.severity === "nice_to_have" ? 5 : 15), 0)
      )
    );
    return {
      passed: pass.length,
      total: active.length,
      failed: fail,
      selectedForBootstrap: selBoot,
      score: showFinalScore ? computedScore : (allRevealed ? computedScore : computedScore),
    };
  }, [report, dismissed, bootstrapSel, revealedNames, allRevealed, showFinalScore]);

  // Group active checks by tier (Essential / Recommended / Optional)
  const tiers = useMemo((): TierGroup[] => {
    if (!report) return [];
    const grouped: Record<TierKey, ReadinessCheck[]> = {
      essential: [],
      recommended: [],
      optional: [],
    };
    for (const check of report.checks) {
      if (dismissed.has(check.name)) continue;
      const tier = SEVERITY_TO_TIER[check.severity] || "optional";
      grouped[tier].push(check);
    }
    const order: TierKey[] = ["essential", "recommended", "optional"];
    return order
      .filter((key) => grouped[key].length > 0)
      .map((key) => ({
        key,
        ...TIER_META[key],
        items: grouped[key],
      }));
  }, [report, dismissed]);

  const tiersWithFailures = tiers.filter((tier) => tier.items.some((c) => !c.passed));
  const tiersAllPass = tiers.filter((tier) => tier.items.every((c) => c.passed));

  const toggleBootstrap = (name: string) => {
    setBootstrapSel((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const dismissCheck = (name: string) => {
    setDismissed((prev) => new Set([...prev, name]));
    setBootstrapSel((prev) => {
      const next = new Set(prev);
      next.delete(name);
      return next;
    });
  };

  const restoreAll = () => {
    setDismissed(new Set());
    if (report) {
      setBootstrapSel(new Set(report.checks.filter((c) => !c.passed).map((c) => c.name)));
    }
  };

  // Error state
  if (error && !report) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-mc-bg font-sans">
        <div className="text-center max-w-[420px]">
          <p className="text-mc-red mb-3 text-sm font-semibold">Failed to scan project</p>
          <p className="text-mc-text-3 text-xs mb-5">{error}</p>
          <div className="flex gap-2 justify-center">
            <Button primary onClick={handleRefresh}>
              {Icons.refresh({ size: 11 })} Try Again
            </Button>
            {onBack && (
              <Button onClick={onBack}>Back to Dashboard</Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full px-6 py-8 font-sans text-mc-text-1 bg-mc-bg min-h-screen">
      {/* Header */}
      <div className="mb-7">
        {onBack && (
          <button
            onClick={onBack}
            className="bg-transparent border-none text-mc-text-3 text-xs font-sans cursor-pointer mb-2 flex items-center gap-1"
          >
            &larr; Back to Dashboard
          </button>
        )}
        <h1 className="text-2xl font-extrabold text-mc-text-0 m-0 tracking-tight">
          Project Readiness
        </h1>
        <p className="text-xs text-mc-text-3 mt-1 mb-0">
          {scanning ? "Scanning your project..." : "Checking if your project is ready for Claude Code"}
        </p>
      </div>

      {/* Score Card */}
      <div className="px-8 py-7 rounded-[14px] bg-mc-surface-1 border border-mc-border-0 mb-6 text-center">
        <div className="flex justify-center mb-4">
          {scanning ? (
            <div className="relative w-[120px] h-[120px]">
              <div
                className="w-full h-full rounded-full border-[6px] border-mc-surface-3 border-t-mc-accent animate-spin"
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-mc-text-3 text-xs font-mono">Scanning</span>
              </div>
            </div>
          ) : (
            <ReadinessRing score={score} size={120} />
          )}
        </div>
        <div className="text-[13px] text-mc-text-2">
          {scanning
            ? "Analyzing project structure..."
            : allRevealed
              ? `${passed} of ${total} checks passed`
              : `Grading... ${revealedCount} of ${total}`
          }
        </div>
        {!scanning && allRevealed && showFinalScore && score >= 80 && failed.length === 0 && (
          <div className="text-xs text-mc-green mt-1.5 flex items-center justify-center gap-1 animate-fade-in">
            {Icons.check({ size: 10, color: t.green })} Project is ready for Claude Code!
          </div>
        )}
      </div>

      {/* Needs Attention Callout — only show after reveal is complete */}
      {!scanning && allRevealed && failed.length > 0 && (
        <div className="px-4 py-3 rounded-[10px] bg-mc-amber-muted border border-mc-amber-border mb-5 flex items-center gap-3 animate-fade-in">
          <span className="text-[13px] font-bold text-mc-amber">{failed.length}</span>
          <span className="text-xs text-mc-text-1 flex-1">
            {failed.length === 1 ? "item needs attention" : "items need attention"}
            {" · "}
            {selectedForBootstrap.length} selected for bootstrap
            {failed.filter((c) => c.severity === "nice_to_have").length > 0 &&
              ` · ${failed.filter((c) => c.severity === "nice_to_have").length} optional`}
          </span>
        </div>
      )}

      {/* Scanning placeholder */}
      {scanning && (
        <div className="flex flex-col gap-3">
          {["Essential", "Recommended", "Optional"].map((label) => (
            <div key={label} className="rounded-xl bg-mc-surface-1 border border-mc-border-0 overflow-hidden">
              <div className="px-[18px] py-3 flex items-center gap-2.5">
                <span className="text-sm font-bold text-mc-text-0">{label}</span>
                <div className="flex-1" />
                <div className="w-16 h-4 bg-mc-surface-3 rounded animate-pulse" />
              </div>
              <div className="px-2.5 pb-2.5 flex flex-col gap-1">
                {[1, 2].map((n) => (
                  <div key={n} className="flex items-center gap-2.5 px-3 py-3 rounded-lg bg-mc-surface-2 border border-mc-border-0">
                    <div className="w-[18px] h-[18px] rounded bg-mc-surface-3 animate-pulse" />
                    <div className="flex-1 flex flex-col gap-1.5">
                      <div className="w-24 h-3 bg-mc-surface-3 rounded animate-pulse" />
                      <div className="w-48 h-2.5 bg-mc-surface-3 rounded animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Check Tiers — revealed progressively */}
      {!scanning && report && (
        <div className="flex flex-col gap-3">
          {/* Tiers with failures (expanded) */}
          {tiersWithFailures.map((tier) => (
            <div
              key={tier.key}
              className="rounded-xl bg-mc-surface-1 overflow-hidden"
              style={{ border: `1px solid ${tier.borderColor}` }}
            >
              <div className="px-[18px] py-3 flex items-center gap-2.5">
                <span className="text-sm font-bold text-mc-text-0">{tier.label}</span>
                <span className="text-[11px] text-mc-text-3">{tier.description}</span>
                <div className="flex-1" />
                <Tag color={tier.tagColor} bg={tier.tagBg}>
                  {tier.items.filter((c) => c.passed && revealedNames.has(c.name)).length}/{tier.items.filter((c) => revealedNames.has(c.name)).length}
                </Tag>
              </div>
              <div className="px-2.5 pb-2.5">
                {tier.items.map((item, ii) => {
                  const isRevealed = revealedNames.has(item.name);
                  const isCheckedForBootstrap = bootstrapSel.has(item.name);

                  // Not yet revealed — show scanning placeholder
                  if (!isRevealed) {
                    return (
                      <div
                        key={ii}
                        className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-mc-surface-2 border border-mc-border-0 ${ii < tier.items.length - 1 ? "mb-1" : ""}`}
                      >
                        <div className="w-[18px] h-[18px] rounded bg-mc-surface-3 animate-pulse shrink-0" />
                        <span className="text-[13px] font-semibold text-mc-text-3">{item.name}</span>
                        <span className="text-[10px] text-mc-text-3 font-mono ml-auto">grading...</span>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={ii}
                      className={`flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-mc-surface-2 animate-fade-in ${ii < tier.items.length - 1 ? "mb-1" : ""}`}
                      style={{
                        border: `1px solid ${item.passed ? t.border0 : tier.borderColor}`,
                      }}
                    >
                      {/* Checkbox for failed items / green circle for passing */}
                      {!item.passed ? (
                        <div
                          onClick={() => toggleBootstrap(item.name)}
                          className={`w-[18px] h-[18px] rounded shrink-0 mt-0.5 cursor-pointer flex items-center justify-center transition-all ${
                            isCheckedForBootstrap
                              ? "bg-mc-accent border-none"
                              : "bg-transparent border-[1.5px] border-mc-border-2"
                          }`}
                        >
                          {isCheckedForBootstrap && (
                            <span className="text-white text-[9px]">{Icons.check({ size: 9, color: "#fff" })}</span>
                          )}
                        </div>
                      ) : (
                        <div className="w-[22px] h-[22px] rounded-full shrink-0 mt-px flex items-center justify-center bg-mc-green text-white text-[10px]">
                          {Icons.check({ size: 10, color: "#fff" })}
                        </div>
                      )}

                      {/* Item content */}
                      <div
                        className={`flex-1 transition-opacity ${
                          !item.passed && !isCheckedForBootstrap ? "opacity-50" : "opacity-100"
                        }`}
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="text-[13px] font-semibold text-mc-text-0">{item.name}</span>
                          <Tag>
                            {CATEGORY_NAMES[item.category] || item.category}
                          </Tag>
                        </div>
                        <div className="text-[11px] text-mc-text-3 mt-0.5">{item.message}</div>

                        {/* Why field */}
                        {!item.passed && item.why && (
                          <div className="text-[11px] text-mc-text-2 mt-1 leading-[1.45] py-1 pb-0.5 border-t border-mc-border-0">
                            {item.why}
                          </div>
                        )}

                        {/* Remediation hint */}
                        {!item.passed && item.remediation && (
                          <div className="text-[11px] text-mc-accent mt-1.5 inline-flex items-center gap-[5px] px-2.5 py-1 rounded-md bg-mc-accent-muted border border-mc-accent-border font-sans font-semibold">
                            {Icons.arrow({ size: 10, color: t.accent })} {item.remediation}
                          </div>
                        )}
                      </div>

                      {/* Dismiss */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {!item.passed && (
                          <button
                            onClick={() => dismissCheck(item.name)}
                            title="Dismiss -- exclude from readiness score"
                            className="bg-transparent border-none cursor-pointer text-mc-text-3 text-[10px] px-1 py-0.5 flex items-center gap-[3px] font-mono opacity-60 hover:opacity-100 transition-opacity"
                          >
                            {Icons.x({ size: 8 })} dismiss
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {/* All-passing tiers (compact strip) — only show after all revealed */}
          {allRevealed && tiersAllPass.length > 0 && (
            <div className="rounded-xl bg-mc-surface-1 border border-mc-border-0 overflow-hidden animate-fade-in">
              <div className="px-[18px] py-3 flex items-center gap-2.5">
                <span className="text-xs font-bold text-mc-text-2">Passing Checks</span>
                <div className="flex-1" />
                <Tag color={t.green} bg={t.greenMuted}>
                  {tiersAllPass.reduce((s, tier) => s + tier.items.length, 0)} passed
                </Tag>
              </div>
              <div className="px-2.5 pb-2.5 flex flex-col gap-0.5">
                {tiersAllPass.map((tier) =>
                  tier.items.map((item, ii) => (
                    <div
                      key={`${tier.key}-${ii}`}
                      className="flex items-center gap-2 py-[7px] px-3 rounded-md"
                    >
                      <div className="w-4 h-4 rounded-full shrink-0 flex items-center justify-center bg-mc-green text-white text-[8px]">
                        {Icons.check({ size: 8, color: "#fff" })}
                      </div>
                      <span className="text-xs font-semibold text-mc-text-2">
                        {item.name}
                      </span>
                      <Tag>
                        {CATEGORY_NAMES[item.category] || item.category}
                      </Tag>
                      <span className="text-[11px] text-mc-text-3 flex-1">
                        {item.message}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Dismissed strip */}
          {allRevealed && dismissed.size > 0 && (
            <div className="px-[18px] py-2.5 rounded-[10px] bg-mc-surface-1 border border-mc-border-0 flex items-center gap-2.5">
              <span className="text-[11px] text-mc-text-3">{dismissed.size} dismissed</span>
              <div className="flex-1" />
              <button
                onClick={restoreAll}
                className="text-[10px] font-mono text-mc-text-3 bg-transparent border-none cursor-pointer underline"
              >
                restore all
              </button>
            </div>
          )}
        </div>
      )}

      {/* Action Bar — only show after reveal is complete */}
      {!scanning && allRevealed && showFinalScore && (
        <div className="flex gap-2.5 justify-center mt-7 pt-5 border-t border-mc-border-0 animate-fade-in">
          {failed.length > 0 && selectedForBootstrap.length > 0 && (
            <Button
              primary
              onClick={onBootstrap}
              className="px-6 py-2.5"
            >
              {Icons.bolt({ size: 11, color: "#fff" })} Bootstrap {selectedForBootstrap.length} Item
              {selectedForBootstrap.length !== 1 ? "s" : ""}
            </Button>
          )}
          {score >= 80 && failed.length === 0 && (
            <Button primary onClick={onSkip} className="px-6 py-2.5">
              Continue to Dashboard
            </Button>
          )}
          <Button onClick={handleRefresh}>
            {Icons.refresh({ size: 11 })} Re-scan
          </Button>
          {!(score >= 80 && failed.length === 0) && (
            <Button onClick={onSkip} className="text-mc-text-3">Back to Dashboard</Button>
          )}
        </div>
      )}
    </div>
  );
}
