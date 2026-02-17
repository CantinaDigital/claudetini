import { useCallback, useEffect, useState } from "react";
import type { ProductMapResponse, ProductFeature } from "../../types";
import { api, isBackendConnected } from "../../api/backend";
import { useProjectManager } from "../../managers/projectManager";
import { t } from "../../styles/tokens";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";

// ── Helpers ──────────────────────────────────────────────────────────

function statusColor(status: string): string {
  if (status === "active") return t.green;
  if (status === "planned") return t.cyan;
  if (status === "deprecated") return t.text3;
  return t.text2;
}

function readinessColor(readiness: number): string {
  if (readiness >= 80) return t.green;
  if (readiness >= 50) return t.amber;
  return t.red;
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "..." : text;
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

  // Generate handler
  const handleGenerate = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) return;
    setIsScanning(true);
    setError(null);
    try {
      const result = await api.scanProductMap(projectPath);
      setProductMap(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Product map generation failed");
    } finally {
      setIsScanning(false);
    }
  }, [projectPath]);

  const handleFeatureFix = (feature: ProductFeature) => {
    if (!onFix) return;
    const gaps = feature.lacks.length > 0
      ? feature.lacks.join(", ")
      : "Improve readiness score";
    onFix(
      "product-map",
      `Improve "${feature.name}" feature: ${gaps}`,
    );
  };

  // Loading state
  if (isLoading && !productMap) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  // Empty state
  if (!productMap && !isLoading && !isScanning && !error) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
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
          <Button primary onClick={handleGenerate} disabled={isScanning}>
            Generate Product Map
          </Button>
          <span className="text-[10px] text-mc-text-3 font-mono">
            Takes 1-3 minutes. Uses Claude Code to analyze the project.
          </span>
        </div>
      </div>
    );
  }

  // Scanning state
  if (isScanning) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="animate-spin text-mc-accent">{Icons.refresh({ size: 28 })}</span>
          <p className="text-sm text-mc-text-1 font-mono text-center">
            Claude is analyzing your project...
          </p>
          <p className="text-[10px] text-mc-text-3 font-mono text-center max-w-xs">
            Reading source code, CLAUDE.md, ROADMAP.md, and git history
            to build a product-level feature map.
          </p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !productMap) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-red">{Icons.alert({ size: 32 })}</span>
          <p className="text-sm text-mc-red font-mono text-center max-w-md">{error}</p>
          <Button onClick={handleGenerate}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!productMap) return null;

  const features = productMap.features;
  const activeCount = features.filter(f => f.status === "active").length;
  const plannedCount = features.filter(f => f.status === "planned").length;

  return (
    <div className="max-w-[960px] mx-auto p-6 flex flex-col gap-5">
      {/* Header */}
      <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl p-5">
        <div className="flex items-center gap-4">
          {/* Avg readiness ring */}
          <div className="relative flex-shrink-0" style={{ width: 56, height: 56 }}>
            <svg width={56} height={56} viewBox="0 0 56 56" className="-rotate-90">
              <circle cx={28} cy={28} r={22} fill="none" stroke={t.surface3} strokeWidth={4} />
              <circle
                cx={28} cy={28} r={22} fill="none"
                stroke={readinessColor(productMap.avg_readiness)}
                strokeWidth={4}
                strokeDasharray={2 * Math.PI * 22}
                strokeDashoffset={2 * Math.PI * 22 * (1 - productMap.avg_readiness / 100)}
                strokeLinecap="round"
                className="transition-all duration-500"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span
                className="text-base font-extrabold font-mono"
                style={{ color: readinessColor(productMap.avg_readiness) }}
              >
                {productMap.avg_readiness}
              </span>
            </div>
          </div>

          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-mc-text-0">Product Map</h2>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-[10px] font-mono text-mc-text-3">
                {features.length} features
              </span>
              <span className="text-[10px] font-mono" style={{ color: t.green }}>
                {activeCount} active
              </span>
              {plannedCount > 0 && (
                <span className="text-[10px] font-mono" style={{ color: t.cyan }}>
                  {plannedCount} planned
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] text-mc-text-3 font-mono">
              {new Date(productMap.generated_at).toLocaleDateString()}
            </span>
            <Button small onClick={handleGenerate} disabled={isScanning}>
              {isScanning ? "Analyzing..." : "Regenerate"}
            </Button>
          </div>
        </div>
      </div>

      {/* Feature list */}
      <div className="flex flex-col gap-2">
        {features.map((feature) => {
          const isExpanded = expandedFeature === feature.name;
          const rColor = readinessColor(feature.readiness);

          return (
            <div
              key={feature.name}
              className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden"
            >
              {/* Feature header */}
              <button
                type="button"
                onClick={() => setExpandedFeature(isExpanded ? null : feature.name)}
                className="flex items-center gap-3 w-full px-4 py-3 text-left hover:bg-mc-surface-2 transition-colors cursor-pointer"
              >
                {/* Status dot */}
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: statusColor(feature.status) }}
                  title={feature.status}
                />

                {/* Name + desc */}
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-semibold text-mc-text-0 block truncate">
                    {feature.name}
                  </span>
                  <span className="text-[10px] text-mc-text-3 block truncate">
                    {truncate(feature.desc, 80)}
                  </span>
                </div>

                {/* Stats */}
                <span className="text-[10px] font-mono text-mc-text-3 flex-shrink-0">
                  {feature.files} files
                </span>
                {feature.tests > 0 && (
                  <span className="text-[10px] font-mono text-mc-green flex-shrink-0">
                    {feature.tests} tests
                  </span>
                )}

                {/* Readiness bar */}
                <div className="w-20 flex items-center gap-1.5 flex-shrink-0">
                  <div className="flex-1 h-1.5 rounded-full bg-mc-surface-3 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{ width: `${feature.readiness}%`, backgroundColor: rColor }}
                    />
                  </div>
                  <span className="text-[10px] font-mono font-bold w-6 text-right" style={{ color: rColor }}>
                    {feature.readiness}
                  </span>
                </div>

                {/* Momentum */}
                {feature.momentum?.commits > 0 && (
                  <span className="text-[9px] font-mono text-mc-accent flex-shrink-0">
                    +{feature.momentum.commits}
                  </span>
                )}

                {/* Chevron */}
                <span className="flex-shrink-0 text-mc-text-3">
                  {Icons.chevDown({ size: 9, open: isExpanded })}
                </span>
              </button>

              {/* Expanded details */}
              {isExpanded && (
                <div className="border-t border-mc-border-0 px-4 py-3 bg-mc-surface-0 animate-fade-in">
                  <div className="grid grid-cols-2 gap-4">
                    {/* Left: readiness detail */}
                    <div>
                      <span className="mc-label block mb-2">Readiness Breakdown</span>
                      {feature.readinessDetail.length > 0 ? (
                        <div className="flex flex-col gap-1.5">
                          {feature.readinessDetail.map((rd, i) => (
                            <div key={i} className="flex items-start gap-2">
                              <span className="text-[10px] font-mono text-mc-text-2 w-20 flex-shrink-0">
                                {rd.dim}
                              </span>
                              <span className="text-[10px] font-mono text-mc-green flex-shrink-0">
                                {rd.have}
                              </span>
                              <span className="text-[10px] text-mc-text-3">→</span>
                              <span className="text-[10px] font-mono text-mc-amber">
                                {rd.need}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[10px] text-mc-text-3 font-mono">No detail available</span>
                      )}

                      {/* Gaps */}
                      {feature.lacks.length > 0 && (
                        <div className="mt-3">
                          <span className="mc-label block mb-1.5">Gaps to Production</span>
                          <div className="flex flex-wrap gap-1">
                            {feature.lacks.map((lack, i) => (
                              <span
                                key={i}
                                className="mc-tag bg-mc-amber-muted text-mc-amber border border-mc-amber-border text-[9px]"
                              >
                                {lack}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Right: dependencies + meta */}
                    <div>
                      {/* Dependencies */}
                      {(feature.dependsOn.length > 0 || feature.dependedBy.length > 0) && (
                        <div className="mb-3">
                          <span className="mc-label block mb-1.5">Dependencies</span>
                          {feature.dependsOn.length > 0 && (
                            <div className="mb-1">
                              <span className="text-[9px] text-mc-text-3">Depends on: </span>
                              {feature.dependsOn.map((dep, i) => (
                                <span key={i} className="text-[10px] font-mono text-mc-text-1">
                                  {dep}{i < feature.dependsOn.length - 1 ? ", " : ""}
                                </span>
                              ))}
                            </div>
                          )}
                          {feature.dependedBy.length > 0 && (
                            <div>
                              <span className="text-[9px] text-mc-text-3">Depended by: </span>
                              {feature.dependedBy.map((dep, i) => (
                                <span key={i} className="text-[10px] font-mono text-mc-text-1">
                                  {dep}{i < feature.dependedBy.length - 1 ? ", " : ""}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Integrations */}
                      {feature.integrations.length > 0 && (
                        <div className="mb-3">
                          <span className="mc-label block mb-1.5">Integrations</span>
                          <div className="flex flex-wrap gap-1">
                            {feature.integrations.map((intg, i) => (
                              <span
                                key={i}
                                className="mc-tag bg-mc-cyan-muted text-mc-cyan border border-mc-cyan-border text-[9px]"
                              >
                                {intg}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Meta row */}
                      <div className="flex items-center gap-3 flex-wrap">
                        {feature.roadmapRef && (
                          <span className="text-[9px] font-mono text-mc-accent" title="Roadmap reference">
                            {feature.roadmapRef}
                          </span>
                        )}
                        {feature.lastTouched && (
                          <span className="text-[9px] font-mono text-mc-text-3">
                            Last: {feature.lastTouched}
                          </span>
                        )}
                        <span
                          className="mc-tag text-[9px]"
                          style={{
                            backgroundColor: statusColor(feature.status) + "20",
                            color: statusColor(feature.status),
                          }}
                        >
                          {feature.status}
                        </span>
                      </div>

                      {/* Fix button */}
                      {onFix && feature.lacks.length > 0 && (
                        <button
                          type="button"
                          onClick={() => handleFeatureFix(feature)}
                          className="mt-3 text-[10px] font-mono text-mc-accent hover:text-mc-text-0 cursor-pointer transition-colors"
                        >
                          Fix gaps
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
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
