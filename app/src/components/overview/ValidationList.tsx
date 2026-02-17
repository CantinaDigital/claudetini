import { InlineMarkdown } from "../ui/InlineMarkdown";
import type { HealthData, GateData, Status } from "../../types";

interface ValidationListProps {
  health: HealthData[];
  gates: GateData[];
}

function getStatusIcon(status: Status): { icon: string; colorClass: string } {
  switch (status) {
    case "pass":
      return { icon: "\u2713", colorClass: "text-mc-green" };
    case "warn":
      return { icon: "\u26A0", colorClass: "text-mc-amber" };
    case "fail":
      return { icon: "\u2717", colorClass: "text-mc-red" };
    default:
      return { icon: "?", colorClass: "text-mc-text-3" };
  }
}

export function ValidationList({ health, gates }: ValidationListProps) {
  const allItems = [
    ...health.map((h) => ({ ...h, isGate: false })),
    ...gates.map((g) => ({ name: `${g.name} Gate`, status: g.status, detail: g.detail, isGate: true })),
  ];

  const passCount = allItems.filter((i) => i.status === "pass").length;
  const warnCount = allItems.filter((i) => i.status === "warn").length;
  const failCount = allItems.filter((i) => i.status === "fail").length;

  if (allItems.length === 0) {
    return (
      <div className="p-4 text-mc-text-3 text-[11px] text-center">
        No validation data available
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="py-2.5 px-3.5 border-b border-mc-border-0 flex items-center justify-between">
        <span className="mc-label">Validation</span>
        <span className="text-[10px] font-mono text-mc-text-3">
          <span className="text-mc-green">{passCount} pass</span>
          {warnCount > 0 && (
            <>
              {" \u00B7 "}
              <span className="text-mc-amber">{warnCount} warn</span>
            </>
          )}
          {failCount > 0 && (
            <>
              {" \u00B7 "}
              <span className="text-mc-red">{failCount} fail</span>
            </>
          )}
        </span>
      </div>

      {/* Validation items */}
      <div className="py-1">
        {allItems.map((item, idx) => {
          const { icon, colorClass } = getStatusIcon(item.status);
          const isFail = item.status === "fail";

          return (
            <div
              key={`${item.name}-${idx}`}
              className={`flex items-center gap-2.5 py-1.5 px-3.5 ${isFail ? "bg-mc-red-muted" : ""} ${idx < allItems.length - 1 ? "border-b border-mc-border-0" : ""}`}
            >
              <span className={`text-xs font-mono font-semibold w-4 text-center shrink-0 ${colorClass}`}>
                {icon}
              </span>
              <span className="text-[11.5px] font-medium text-mc-text-1 flex-1 min-w-0 truncate">
                {item.name}
              </span>
              {item.detail && (
                <span className="text-[10px] text-mc-text-3 max-w-[160px] truncate shrink-0">
                  <InlineMarkdown>{item.detail}</InlineMarkdown>
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
