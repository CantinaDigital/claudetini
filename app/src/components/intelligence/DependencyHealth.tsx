import { useState, useMemo } from "react";
import type {
  DependencyReport,
  DependencyPackage,
  DependencyVulnerability,
} from "../../types";
import { Icons } from "../ui/Icons";
import { SkeletonText } from "../ui/SkeletonLoader";

interface DependencyHealthProps {
  ecosystems: DependencyReport[];
  isLoading?: boolean;
}

type DepFilter = "all" | "outdated" | "vulnerable";

interface PackageCard {
  pkg: DependencyPackage;
  ecosystem: string;
  vulnerabilities: DependencyVulnerability[];
}

const updateSeverityStyles: Record<string, string> = {
  major: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  minor: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  patch: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

const vulnSeverityStyles: Record<string, string> = {
  critical: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  high: "bg-mc-red-muted text-mc-red border border-mc-red-border",
  medium: "bg-mc-amber-muted text-mc-amber border border-mc-amber-border",
  low: "bg-mc-surface-2 text-mc-text-3 border border-mc-border-1",
};

function buildCards(ecosystems: DependencyReport[]): PackageCard[] {
  const cards: PackageCard[] = [];

  for (const eco of ecosystems) {
    // Map vulns to package names
    const vulnsByPkg = new Map<string, DependencyVulnerability[]>();
    for (const v of eco.vulnerabilities) {
      const existing = vulnsByPkg.get(v.package_name) || [];
      existing.push(v);
      vulnsByPkg.set(v.package_name, existing);
    }

    // Outdated packages
    for (const pkg of eco.outdated) {
      cards.push({
        pkg,
        ecosystem: eco.ecosystem,
        vulnerabilities: vulnsByPkg.get(pkg.name) || [],
      });
      // Remove from vulns map so we don't double-add
      vulnsByPkg.delete(pkg.name);
    }

    // Vulnerable-only packages (not already in outdated)
    for (const [pkgName, vulns] of vulnsByPkg) {
      cards.push({
        pkg: {
          name: pkgName,
          current_version: "",
          latest_version: "",
          update_severity: null,
          ecosystem: eco.ecosystem as DependencyPackage["ecosystem"],
          is_dev: false,
        },
        ecosystem: eco.ecosystem,
        vulnerabilities: vulns,
      });
    }
  }

  // Sort: vulnerabilities first, then outdated
  cards.sort((a, b) => {
    const aVuln = a.vulnerabilities.length > 0 ? 1 : 0;
    const bVuln = b.vulnerabilities.length > 0 ? 1 : 0;
    if (aVuln !== bVuln) return bVuln - aVuln;
    // Then by update severity
    const sevOrder: Record<string, number> = { major: 0, minor: 1, patch: 2 };
    const aOrd = a.pkg.update_severity ? (sevOrder[a.pkg.update_severity] ?? 3) : 3;
    const bOrd = b.pkg.update_severity ? (sevOrder[b.pkg.update_severity] ?? 3) : 3;
    return aOrd - bOrd;
  });

  return cards;
}

export function DependencyHealth({ ecosystems, isLoading }: DependencyHealthProps) {
  const [filter, setFilter] = useState<DepFilter>("all");
  const [expandedPkg, setExpandedPkg] = useState<string | null>(null);

  const allCards = useMemo(() => buildCards(ecosystems), [ecosystems]);

  const counts = useMemo(() => {
    let outdated = 0;
    let vulnerable = 0;
    for (const card of allCards) {
      if (card.vulnerabilities.length > 0) vulnerable++;
      if (card.pkg.update_severity) outdated++;
    }
    return { all: allCards.length, outdated, vulnerable };
  }, [allCards]);

  const filtered = useMemo(() => {
    if (filter === "outdated") {
      return allCards.filter((c) => c.pkg.update_severity !== null);
    }
    if (filter === "vulnerable") {
      return allCards.filter((c) => c.vulnerabilities.length > 0);
    }
    return allCards;
  }, [allCards, filter]);

  if (isLoading) {
    return (
      <div className="p-4">
        <SkeletonText lines={6} />
      </div>
    );
  }

  const filterPills: { key: DepFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "outdated", label: "Outdated" },
    { key: "vulnerable", label: "Vulnerable" },
  ];

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Filter pills */}
      <div className="flex bg-mc-surface-2 border border-mc-border-1 rounded-lg overflow-hidden w-fit">
        {filterPills.map((pill) => (
          <button
            key={pill.key}
            type="button"
            onClick={() => setFilter(pill.key)}
            className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold transition-colors flex items-center gap-1 ${
              filter === pill.key
                ? pill.key === "vulnerable"
                  ? "bg-mc-red-muted text-mc-red"
                  : pill.key === "outdated"
                    ? "bg-mc-amber-muted text-mc-amber"
                    : "bg-mc-accent-muted text-mc-accent"
                : "text-mc-text-3 hover:text-mc-text-1"
            }`}
          >
            {pill.label}
            <span className="font-bold">{counts[pill.key]}</span>
          </button>
        ))}
      </div>

      {/* Package count */}
      <div className="text-[10px] text-mc-text-3 font-mono">
        {filtered.length} package{filtered.length !== 1 ? "s" : ""}
      </div>

      {/* Cards grid */}
      {filtered.length === 0 ? (
        <div className="text-xs text-mc-text-3 font-mono text-center py-8">
          No dependency issues found
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {filtered.map((card) => {
            const hasVulns = card.vulnerabilities.length > 0;
            const cardKey = `${card.ecosystem}:${card.pkg.name}`;
            const isExpanded = expandedPkg === cardKey;

            return (
              <button
                key={cardKey}
                type="button"
                onClick={() => setExpandedPkg(isExpanded ? null : cardKey)}
                className={`text-left rounded-xl p-3 transition-colors cursor-pointer ${
                  hasVulns
                    ? "bg-mc-red-muted border border-mc-red-border hover:bg-mc-surface-2"
                    : "bg-mc-surface-1 border border-mc-border-0 hover:bg-mc-surface-2"
                }`}
              >
                {/* Header */}
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-xs font-semibold text-mc-text-0 truncate flex-1">
                    {card.pkg.name}
                  </span>
                  <span className="mc-tag bg-mc-surface-2 text-mc-text-3 border border-mc-border-1 flex-shrink-0">
                    {card.ecosystem}
                  </span>
                </div>

                {/* Version info */}
                {card.pkg.current_version && (
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="text-[11px] font-mono text-mc-text-2">
                      {card.pkg.current_version}
                    </span>
                    {card.pkg.latest_version && (
                      <>
                        <span className="text-mc-text-3">
                          {Icons.arrow({ size: 10 })}
                        </span>
                        <span className="text-[11px] font-mono text-mc-text-1 font-semibold">
                          {card.pkg.latest_version}
                        </span>
                      </>
                    )}
                    {card.pkg.update_severity && (
                      <span
                        className={`mc-severity-tag ${updateSeverityStyles[card.pkg.update_severity] || updateSeverityStyles.patch}`}
                      >
                        {card.pkg.update_severity.toUpperCase()}
                      </span>
                    )}
                  </div>
                )}

                {/* Vulnerability summary */}
                {hasVulns && (
                  <div className="flex flex-col gap-1">
                    {card.vulnerabilities.map((vuln, i) => (
                      <div
                        key={vuln.advisory_id || i}
                        className="flex items-center gap-1.5"
                      >
                        <span className="text-mc-red flex-shrink-0">
                          {Icons.alert({ size: 10 })}
                        </span>
                        <span className="text-[10px] font-mono text-mc-red truncate flex-1">
                          {vuln.title}
                        </span>
                        <span
                          className={`mc-severity-tag flex-shrink-0 ${vulnSeverityStyles[vuln.severity] || vulnSeverityStyles.low}`}
                        >
                          {vuln.severity.toUpperCase()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Expanded details */}
                {isExpanded && hasVulns && (
                  <div className="mt-3 pt-2 border-t border-mc-border-0 animate-fade-in">
                    {card.vulnerabilities.map((vuln, i) => (
                      <div key={vuln.advisory_id || i} className="mb-2 last:mb-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`mc-severity-tag ${vulnSeverityStyles[vuln.severity] || vulnSeverityStyles.low}`}
                          >
                            {vuln.severity.toUpperCase()}
                          </span>
                          <span className="text-[10px] font-mono text-mc-text-3">
                            {vuln.advisory_id}
                          </span>
                        </div>
                        <p className="text-xs text-mc-text-1 mb-1">
                          {vuln.title}
                        </p>
                        {vuln.fixed_in && (
                          <span className="text-[10px] font-mono text-mc-green">
                            Fixed in {vuln.fixed_in}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
