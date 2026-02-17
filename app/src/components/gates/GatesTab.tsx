import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { SeverityTag } from "../ui/SeverityTag";
import { Button } from "../ui/Button";
import { Toggle } from "../ui/Toggle";
import { Icons } from "../ui/Icons";
import { Sparkline } from "../ui/Sparkline";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { api, isBackendConnected } from "../../api/backend";
import { useSettingsStore } from "../../stores/settingsStore";

type GateStatus = "pass" | "warn" | "fail" | "skipped" | "error";

const GATE_ICONS: Record<string, string> = {
  secrets: "🔐",
  tests: "🧪",
  lint: "✨",
  typecheck: "📐",
  types: "📐",
  security: "🔒",
  documentation: "📄",
  docs: "📄",
  test_coverage: "📊",
};

interface GateUI {
  name: string;
  icon: string;
  status: GateStatus;
  detail: string;
  finding: string | null;
  lastRun: string;
  trend: number[];
}

interface GatesTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  onFix?: (gateName: string, finding: string) => void;
  onNavigateToSettings?: () => void;
}

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function generateTrend(status: GateStatus): number[] {
  const base = status === "pass" ? 1 : status === "warn" ? 0.5 : 0;
  return Array(10).fill(base);
}

/** Strip ANSI escape codes from terminal output */
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  let cleaned = text.replace(/[\x1b\u001b\u009b]\[[0-9;]*[A-Za-z]|[\x1b\u001b\u009b]\([A-Za-z]|[\x1b\u001b\u009b]\][^\x07]*\x07|[\x1b\u001b\u009b][=>]/g, "");
  // Remove any remaining standalone control characters
  // eslint-disable-next-line no-control-regex
  cleaned = cleaned.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");
  return cleaned;
}

export function GatesTab({ projectPath, isActive = true, onFix, onNavigateToSettings }: GatesTabProps) {
  const [gates, setGates] = useState<GateUI[]>([]);
  const [expandedGate, setExpandedGate] = useState<string | null>(null);
  const [focusedGateIndex, setFocusedGateIndex] = useState(-1);
  const gateRefs = useRef<(HTMLDivElement | null)[]>([]);
  const hasLoaded = useRef(false);
  const prePushHook = useSettingsStore((s) => s.prePushHookEnabled);
  const setPrePushHook = useSettingsStore((s) => s.setPrePushHookEnabled);
  const [lastRun, setLastRun] = useState<string>("Never");
  const [filesScanned, setFilesScanned] = useState(0);
  const [gateCost, setGateCost] = useState<string>("N/A");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gateHistory, setGateHistory] = useState<Record<string, { score: number }[]>>({});

  const mapReport = (report: Awaited<ReturnType<typeof api.getGateResults>>, history?: Record<string, { score: number }[]>) => {
    const hist = history || gateHistory;
    const mappedGates: GateUI[] = report.gates.map((g) => {
      const gateTrend = hist[g.name.toLowerCase()];
      const trend = gateTrend && gateTrend.length > 0
        ? gateTrend.slice(-10).map((p) => p.score / 100)
        : generateTrend(g.status as GateStatus);
      return {
        name: g.name.charAt(0).toUpperCase() + g.name.slice(1),
        icon: GATE_ICONS[g.name.toLowerCase()] || "⚙️",
        status: g.status as GateStatus,
        detail: stripAnsi(g.message),
        finding: stripAnsi(g.detail || (g.findings.length > 0 ? g.findings[0].description : "") || "") || null,
        lastRun: report.timestamp ? formatRelativeTime(report.timestamp) : "N/A",
        trend,
      };
    });
    setGates(mappedGates);
    setLastRun(report.timestamp ? formatRelativeTime(report.timestamp) : "Never");
    setFilesScanned(report.changedFiles.length);
    const totalCost = report.gates.reduce((sum, gate) => sum + gate.costEstimate, 0);
    setGateCost(Number.isFinite(totalCost) ? `$${totalCost.toFixed(2)}` : "N/A");
  };

  // Reset hasLoaded on project change
  useEffect(() => { hasLoaded.current = false; }, [projectPath]);

  useEffect(() => {
    if (!isActive && !hasLoaded.current) return;

    const fetchData = async () => {
      if (!projectPath || !isBackendConnected()) {
        setLoading(false);
        setGates([]);
        return;
      }

      if (!hasLoaded.current) setLoading(true);
      hasLoaded.current = true;
      setError(null);
      const _t0 = performance.now();
      try {
        // Fetch gate results and history in parallel
        const [report, historyResult] = await Promise.allSettled([
          api.getGateResults(projectPath),
          api.getGateHistory(projectPath),
        ]);

        let history: Record<string, { score: number }[]> = {};
        if (historyResult.status === "fulfilled") {
          // Map GateHistoryPoint[] to { score }[] for trend display
          history = Object.fromEntries(
            Object.entries(historyResult.value).map(([k, v]) => [k, v.map((p) => ({ score: p.score }))])
          );
          setGateHistory(history);
        }

        if (report.status === "fulfilled") {
          mapReport(report.value, history);
        } else {
          throw report.reason;
        }
        console.log(`%c[GatesTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
      } catch (e) {
        console.warn("Failed to fetch gate results:", e);
        setError(e instanceof Error ? e.message : "Failed to load quality gate results");
        setGates([]);
      } finally {
        setLoading(false);
      }
    };

    void fetchData();
  }, [projectPath, isActive]);

  const handleRunGates = async () => {
    if (!projectPath || !isBackendConnected()) return;
    setRunning(true);
    setError(null);
    try {
      const report = await api.runGates(projectPath);
      mapReport(report);
    } catch (e) {
      console.error("Failed to run gates:", e);
      setError(e instanceof Error ? e.message : "Failed to run quality gates");
    } finally {
      setRunning(false);
    }
  };

  const handleFix = (gateName: string, finding: string) => {
    if (onFix) {
      onFix(gateName, finding);
      return;
    }
    console.log(`Fixing issues in ${gateName}: ${finding}`);
  };

  const handleGateKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (gates.length === 0) return;
      let next = focusedGateIndex;

      if (event.key === "ArrowDown") {
        next = Math.min(focusedGateIndex + 1, gates.length - 1);
      } else if (event.key === "ArrowUp") {
        next = Math.max(focusedGateIndex - 1, 0);
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (focusedGateIndex >= 0) {
          const gate = gates[focusedGateIndex];
          if (gate.finding) {
            setExpandedGate((prev) => (prev === gate.name ? null : gate.name));
          }
        }
        return;
      } else {
        return;
      }
      event.preventDefault();
      setFocusedGateIndex(next);
      gateRefs.current[next]?.focus();
    },
    [focusedGateIndex, gates],
  );

  const handleConfigure = () => {
    onNavigateToSettings?.();
  };

  if (loading) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Loading quality gates...
      </div>
    );
  }

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view quality gates.
      </div>
    );
  }

  return (
    <div className="w-full animate-fade-in">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2.5">
          <span className="text-xs text-mc-text-3">
            Last run: {lastRun} · {filesScanned} files
          </span>
          <span className="text-[11px] font-mono text-mc-text-3">{gateCost}</span>
        </div>
        <div className="flex gap-2">
          <Button small onClick={handleConfigure}>Configure</Button>
          <Button primary onClick={handleRunGates} disabled={running}>
            {running ? "Running..." : <><Icons.play size={10} /> Run All</>}
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-2.5 px-2.5 py-2 rounded-lg bg-mc-red-muted border border-mc-red-border text-mc-red text-xs">
          {error}
        </div>
      )}

      {gates.length === 0 ? (
        <div className="p-4 rounded-[10px] border border-mc-border-0 bg-mc-surface-1 text-mc-text-3 text-xs">
          No quality gate results are available yet.
        </div>
      ) : (
        <div className="flex flex-col gap-1.5" role="list" aria-label="Quality gates">
          {gates.map((gate, gi) => {
            const isExpanded = expandedGate === gate.name;
            const isFocused = focusedGateIndex === gi;
            const statusColor = gate.status === "pass" ? t.green : gate.status === "warn" ? t.amber : t.red;
            const borderClass = isFocused
              ? "border-mc-accent-border"
              : gate.status === "fail"
              ? "border-mc-red-border"
              : gate.status === "warn"
              ? "border-mc-amber-border"
              : "border-mc-border-0";

            return (
              <div
                key={gate.name}
                ref={(el) => { gateRefs.current[gi] = el; }}
                role="listitem"
                tabIndex={isFocused ? 0 : gi === 0 && focusedGateIndex === -1 ? 0 : -1}
                onFocus={() => setFocusedGateIndex(gi)}
                onKeyDown={handleGateKeyDown}
                className={`bg-mc-surface-1 border ${borderClass} rounded-[10px] overflow-hidden outline-none`}
              >
                <div
                  onClick={() => gate.finding && setExpandedGate((prev) => (prev === gate.name ? null : gate.name))}
                  className={`flex items-center gap-3 px-4 py-3 ${gate.finding ? "cursor-pointer" : "cursor-default"}`}
                >
                  <span className="text-[18px] shrink-0">{gate.icon}</span>
                  <span className="text-[13.5px] font-semibold text-mc-text-0 min-w-[80px]">{gate.name}</span>
                  <SeverityTag status={gate.status} />
                  <span className="text-[11.5px] text-mc-text-3 font-mono flex-1"><InlineMarkdown>{gate.detail}</InlineMarkdown></span>
                  <Sparkline data={gate.trend} color={statusColor} />
                  <span className="text-[10px] text-mc-text-3 font-mono">{gate.lastRun}</span>
                  {gate.finding && (
                    <span className="text-mc-text-3 flex">
                      <Icons.chevDown size={10} color={t.text3} open={isExpanded} />
                    </span>
                  )}
                </div>

                {isExpanded && gate.finding && (
                  <div className="px-4 pb-3.5 pl-12 animate-fade-in-fastest">
                    <div
                      className={`px-3.5 py-2.5 rounded-lg flex items-center gap-3 ${
                        gate.status === "fail"
                          ? "bg-mc-red-muted border border-mc-red-border"
                          : "bg-mc-amber-muted border border-mc-amber-border"
                      }`}
                    >
                      <pre className="text-[11.5px] font-mono text-mc-text-2 leading-[1.5] flex-1 whitespace-pre-wrap break-words m-0">
                        {gate.finding}
                      </pre>
                      <Button
                        primary={gate.status !== "fail"}
                        danger={gate.status === "fail"}
                        small
                        onClick={() => handleFix(gate.name, gate.finding || "")}
                      >
                        <Icons.play size={10} /> Fix
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-[18px] px-4 py-3.5 rounded-[10px] bg-mc-surface-1 border border-mc-border-0 flex justify-between items-center">
        <div>
          <div className="text-[13px] font-semibold text-mc-text-1">Git Pre-Push Hook</div>
          <div className="text-[11px] text-mc-text-3 mt-0.5">Block push when gates fail</div>
        </div>
        <Toggle on={prePushHook} onClick={() => setPrePushHook(!prePushHook)} />

      </div>
    </div>
  );
}
