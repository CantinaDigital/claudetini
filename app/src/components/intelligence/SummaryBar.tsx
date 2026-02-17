import type { IntelligenceReport } from "../../types";
import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";

interface SummaryBarProps {
  report: IntelligenceReport | null;
  isLoading?: boolean;
  onScanClick: () => void | Promise<void>;
  error?: string | null;
}

// Score ring adapted for intelligence display
function ScoreRing({ score }: { score: number }) {
  const size = 56;
  const strokeWidth = 4;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - score / 100);
  const color = score >= 85 ? t.green : score >= 60 ? t.amber : t.red;

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={t.surface3}
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-[600ms] ease"
          style={{ filter: `drop-shadow(0 0 6px ${color}40)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="text-base font-extrabold font-mono leading-none"
          style={{ color }}
        >
          {Math.round(score)}
        </span>
      </div>
    </div>
  );
}

interface CategoryPill {
  name: string;
  count: number;
  severity: "critical" | "warning" | "info";
}

function getCategoryPills(report: IntelligenceReport): CategoryPill[] {
  const hardcodedCritical = report.hardcoded.findings.filter(
    (f) => f.severity === "critical",
  ).length;
  const hardcodedWarn = report.hardcoded.findings.filter(
    (f) => f.severity === "warning",
  ).length;
  const hardcodedCount = report.hardcoded.findings.length;

  const depVulns = report.dependencies.reduce(
    (sum, d) => sum + d.vulnerabilities.length,
    0,
  );
  const depOutdated = report.dependencies.reduce(
    (sum, d) => sum + d.outdated.length,
    0,
  );
  const depCount = depVulns + depOutdated;

  const integrationCount = report.integrations.integrations.length;

  const staleCount =
    report.freshness.stale_files.length +
    report.freshness.abandoned_files.length;

  const untrackedCount = report.features.untracked_features.length;
  const featureTotal = report.features.total_features;

  return [
    {
      name: "Hardcoded",
      count: hardcodedCount,
      severity:
        hardcodedCritical > 0
          ? "critical"
          : hardcodedWarn > 0
            ? "warning"
            : "info",
    },
    {
      name: "Dependencies",
      count: depCount,
      severity: depVulns > 0 ? "critical" : depOutdated > 0 ? "warning" : "info",
    },
    {
      name: "Integrations",
      count: integrationCount,
      severity: "info",
    },
    {
      name: "Freshness",
      count: staleCount,
      severity:
        report.freshness.abandoned_files.length > 0
          ? "critical"
          : staleCount > 0
            ? "warning"
            : "info",
    },
    {
      name: "Features",
      count: untrackedCount > 0 ? untrackedCount : featureTotal,
      severity: untrackedCount > 0 ? "warning" : "info",
    },
  ];
}

const severityStyles: Record<
  "critical" | "warning" | "info",
  string
> = {
  critical: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  warning: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  info: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

function CategoryPillBadge({ pill }: { pill: CategoryPill }) {
  return (
    <span
      className={`mc-tag flex items-center gap-1.5 ${severityStyles[pill.severity]}`}
    >
      {pill.name}
      <span className="font-bold">{pill.count}</span>
    </span>
  );
}

function formatRelativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function SummaryBar({
  report,
  isLoading = false,
  onScanClick,
  error,
}: SummaryBarProps) {
  if (error) {
    return (
      <div className="flex items-center gap-3 px-4 py-4 bg-mc-surface-0 border-b border-mc-border-0">
        <span className="text-mc-red">{Icons.alert({ size: 14 })}</span>
        <span className="text-xs text-mc-red font-mono flex-1 truncate">
          {error}
        </span>
        <Button small onClick={onScanClick} disabled={isLoading}>
          {isLoading ? "Scanning..." : "Retry"}
        </Button>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex items-center gap-3 px-4 py-4 bg-mc-surface-0 border-b border-mc-border-0">
        <span className="text-xs text-mc-text-3 font-mono flex-1">
          No scan data available
        </span>
        <Button small primary onClick={onScanClick} disabled={isLoading}>
          {isLoading ? "Scanning..." : "Scan Now"}
        </Button>
      </div>
    );
  }

  const pills = getCategoryPills(report);

  return (
    <div className="flex items-center gap-4 px-4 py-3 bg-mc-surface-0 border-b border-mc-border-0">
      {/* Score ring */}
      <div className="flex flex-col items-center gap-0.5 flex-shrink-0">
        <ScoreRing score={report.overall_score} />
        <span className="text-[9px] text-mc-text-3 font-mono">
          Intelligence
        </span>
      </div>

      {/* Category pills */}
      <div className="flex-1 flex items-center gap-1.5 flex-wrap min-w-0">
        {pills.map((pill) => (
          <CategoryPillBadge key={pill.name} pill={pill} />
        ))}
      </div>

      {/* Scan info + button */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className="text-[10px] text-mc-text-3 font-mono whitespace-nowrap">
          {formatRelativeTime(report.generated_at)}
        </span>
        <Button small onClick={onScanClick} disabled={isLoading}>
          {isLoading && (
            <span className="animate-spin inline-block">
              {Icons.refresh({ size: 10 })}
            </span>
          )}
          {isLoading ? "Scanning..." : "Scan Now"}
        </Button>
      </div>
    </div>
  );
}
