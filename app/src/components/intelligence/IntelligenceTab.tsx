import { useCallback, useEffect, useState } from "react";
import type { IntelligenceReport } from "../../types";
import { api, isBackendConnected } from "../../api/backend";
import { useProjectManager } from "../../managers/projectManager";
import { SummaryBar } from "./SummaryBar";
import { CollapsibleSection } from "./CollapsibleSection";
import { TechDebtHeatmap } from "./TechDebtHeatmap";
import { HardcodedFindings } from "./HardcodedFindings";
import { DependencyHealth } from "./DependencyHealth";
import { IntegrationsMap } from "./IntegrationsMap";
import { CodeFreshness } from "./CodeFreshness";
import { FeatureMap } from "./FeatureMap";
import { SkeletonCard } from "../ui/SkeletonLoader";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";

const CACHE_KEY = "cantina:intelligence-report";
const CACHE_MAX_AGE_MS = 60 * 60 * 1000; // 1 hour

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
    const cached: CachedReport = {
      projectPath,
      timestamp: Date.now(),
      report,
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cached));
  } catch {
    // localStorage full or unavailable — ignore
  }
}

export default function IntelligenceTab() {
  const projectPath = useProjectManager((s) => s.currentProject?.path) ?? "";

  const [report, setReport] = useState<IntelligenceReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load intelligence data on mount
  useEffect(() => {
    if (!projectPath) return;

    // Check frontend cache first
    const cached = getCachedReport(projectPath);
    if (cached) {
      setReport(cached);
      return;
    }

    if (!isBackendConnected()) return;

    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Try summary first (fast, 5s timeout)
        const summary = await api.getIntelligenceSummary(projectPath);
        if (cancelled) return;

        // If summary exists, fetch full report
        if (summary) {
          const fullReport = await api.getIntelligence(projectPath);
          if (cancelled) return;
          setReport(fullReport);
          setCachedReport(projectPath, fullReport);
        }
      } catch {
        // No cached data on backend — user needs to run a scan
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

  // Loading skeleton
  if (isLoading && !report) {
    return (
      <div className="max-w-[900px] mx-auto" style={{ padding: 24 }}>
        <SummaryBar report={null} isLoading onScanClick={handleScan} />
        <div className="flex flex-col" style={{ gap: 16, marginTop: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  // Empty state
  if (!report && !isLoading && !error) {
    return (
      <div className="max-w-[900px] mx-auto" style={{ padding: 24 }}>
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <span className="text-mc-text-3">
            {Icons.search({ size: 32 })}
          </span>
          <p className="text-sm text-mc-text-2 font-mono text-center">
            No intelligence data. Run a scan to get started.
          </p>
          <Button primary onClick={handleScan}>
            Scan Now
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[900px] mx-auto" style={{ padding: 24 }}>
      {/* Sticky summary bar */}
      <div className="sticky top-0 z-10 -mx-4 px-4 bg-mc-bg">
        <SummaryBar
          report={report}
          isLoading={isLoading}
          onScanClick={handleScan}
          error={error}
        />
      </div>

      {/* Sections */}
      {report && (
        <div className="flex flex-col" style={{ gap: 16, marginTop: 16 }}>
          {/* 1. Tech Debt Heatmap — expanded by default */}
          <CollapsibleSection
            title="Tech Debt Heatmap"
            icon={Icons.alert({ size: 14 })}
            subtitle={`${report.hardcoded.findings.length + report.freshness.stale_files.length + report.freshness.abandoned_files.length} issues`}
            defaultOpen={true}
          >
            <TechDebtHeatmap report={report} />
          </CollapsibleSection>

          {/* 2. Hardcoded Values — collapsed */}
          <CollapsibleSection
            title="Hardcoded Values"
            icon={Icons.lock({ size: 14 })}
            subtitle={`${report.hardcoded.findings.length} findings`}
            defaultOpen={false}
          >
            <HardcodedFindings findings={report.hardcoded.findings} />
          </CollapsibleSection>

          {/* 3. Dependency Health — collapsed */}
          <CollapsibleSection
            title="Dependency Health"
            icon={Icons.folder({ size: 14 })}
            subtitle={`${report.dependencies.length} ecosystems`}
            defaultOpen={false}
          >
            <DependencyHealth ecosystems={report.dependencies} />
          </CollapsibleSection>

          {/* 4. Integrations & APIs — collapsed */}
          <CollapsibleSection
            title="Integrations & APIs"
            icon={Icons.bolt({ size: 14 })}
            subtitle={`${report.integrations.integrations.length} points`}
            defaultOpen={false}
          >
            <IntegrationsMap integrations={report.integrations} />
          </CollapsibleSection>

          {/* 5. Code Freshness — collapsed */}
          <CollapsibleSection
            title="Code Freshness"
            icon={Icons.refresh({ size: 14 })}
            subtitle={`Score: ${Math.round(report.freshness.freshness_score)}%`}
            defaultOpen={false}
          >
            <CodeFreshness freshness={report.freshness} />
          </CollapsibleSection>

          {/* 6. Feature Map — collapsed */}
          <CollapsibleSection
            title="Feature Map"
            icon={Icons.check({ size: 14 })}
            subtitle={`${report.features.total_features} features`}
            defaultOpen={false}
          >
            <FeatureMap features={report.features} />
          </CollapsibleSection>
        </div>
      )}
    </div>
  );
}
