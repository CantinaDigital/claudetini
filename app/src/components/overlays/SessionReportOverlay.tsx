import { Section } from "../ui/Section";
import { StatusDot } from "../ui/StatusDot";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { DiffBlock, looksLikeDiff } from "../ui/DiffBlock";
import type { Status } from "../../types";

export interface SessionReport {
  sessionId: string;
  duration: string;
  cost?: string | null;
  tokens?: { input: number; output: number } | null;
  provider?: string | null;
  branch?: string | null;
  summary: string;
  files: { path: string; status: "A" | "M" | "D"; lines: string }[];
  tests?: { passed: number; failed: number; coverage?: number; newTests?: number } | null;
  gates: Record<string, Status>;
  roadmapMatches?: string[];
}

interface SessionReportOverlayProps {
  report: SessionReport;
  onClose: () => void;
  onApprove?: () => void;
  onRetry?: () => void;
  onRevert?: () => void;
}

const fileStatusClasses: Record<string, { text: string; bg: string }> = {
  A: { text: "text-mc-green", bg: "bg-mc-green/[0.09]" },
  M: { text: "text-mc-amber", bg: "bg-mc-amber/[0.09]" },
  D: { text: "text-mc-red", bg: "bg-mc-red/[0.09]" },
};

export function SessionReportOverlay({
  report,
  onClose,
  onApprove,
  onRetry,
  onRevert,
}: SessionReportOverlayProps) {
  const totalTokens = report.tokens
    ? report.tokens.input + report.tokens.output
    : null;
  const roadmapMatches = report.roadmapMatches || [];
  const gateEntries = Object.entries(report.gates);
  const details = [
    report.duration,
    report.cost || "Cost unavailable",
    totalTokens != null ? `${totalTokens.toLocaleString()} tokens` : "Token usage unavailable",
    report.provider || "provider unavailable",
  ];

  // Shorten session ID for display (UUIDs are too long for the header)
  const shortSessionId = report.sessionId.length > 12
    ? report.sessionId.slice(0, 8)
    : report.sessionId;

  return (
    <div
      className="fixed inset-0 bg-black/60 z-[100] flex justify-end"
      onClick={onClose}
    >
      <div
        className="w-[520px] bg-mc-surface-0 border-l border-mc-border-1 h-full overflow-y-auto animate-slide-in p-[20px_24px] flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <div className="text-[16px] font-extrabold text-mc-text-0">
              Session #{shortSessionId} Report
            </div>
            <div className="text-[11px] text-mc-text-3 font-mono mt-[3px]">
              {details.join(" · ")}
            </div>
          </div>
          <button
            onClick={onClose}
            className="bg-transparent border-none text-mc-text-3 cursor-pointer p-1"
          >
            <Icons.x size={12} />
          </button>
        </div>

        {/* Summary — diff-aware rendering */}
        {looksLikeDiff(report.summary) ? (
          <DiffBlock text={report.summary} maxHeight={260} />
        ) : (
          <div className="text-[12.5px] text-mc-text-1 leading-[1.55]">
            {report.summary.split("\n").map((line, i) => {
              const trimmed = line.trim();
              if (!trimmed) return <br key={i} />;
              // ### headings
              if (trimmed.startsWith("### ")) {
                return (
                  <div key={i} className="text-[11px] font-bold text-mc-text-0 mt-2 mb-1 uppercase tracking-[0.04em]">
                    <InlineMarkdown>{trimmed.slice(4)}</InlineMarkdown>
                  </div>
                );
              }
              // Numbered list items (e.g. "1. **dispatch.py** — ...")
              if (/^\d+\.\s/.test(trimmed)) {
                return (
                  <div key={i} className="pl-2 py-0.5">
                    <InlineMarkdown>{trimmed}</InlineMarkdown>
                  </div>
                );
              }
              // Bullet list items
              if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
                return (
                  <div key={i} className="pl-2 py-0.5">
                    <InlineMarkdown>{trimmed}</InlineMarkdown>
                  </div>
                );
              }
              // Regular paragraph
              return (
                <div key={i}>
                  <InlineMarkdown>{trimmed}</InlineMarkdown>
                </div>
              );
            })}
          </div>
        )}

        {/* Gate Results */}
        {gateEntries.length > 0 ? (
          <div className="flex gap-1.5 flex-wrap">
            {gateEntries.map(([name, status]) => (
              <div
                key={name}
                className="flex items-center gap-[5px] px-2.5 py-1 rounded-[6px] bg-mc-surface-2 border border-mc-border-0"
              >
                <StatusDot status={status} size={5} />
                <span className="text-[11px] font-medium text-mc-text-1 capitalize">
                  {name}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-mc-text-3">No gate results were captured for this session.</div>
        )}

        {/* Tests */}
        {report.tests && (
          <Section label="Tests">
            <div className="px-3.5 py-2.5 flex gap-4 text-xs">
              <span className="text-mc-green font-mono font-semibold">
                {report.tests.passed} passed
              </span>
              <span
                className={`font-mono font-semibold ${
                  report.tests.failed > 0 ? "text-mc-red" : "text-mc-text-3"
                }`}
              >
                {report.tests.failed} failed
              </span>
              {report.tests.coverage != null && (
                <span className="text-mc-text-2 font-mono">
                  {report.tests.coverage}% cov
                </span>
              )}
              {report.tests.newTests != null && (
                <span className="text-mc-accent font-mono">
                  +{report.tests.newTests} new
                </span>
              )}
            </div>
          </Section>
        )}

        {/* Changed Files */}
        <Section label={`Changed Files · ${report.files.length}`}>
          <div className="py-1">
            {report.files.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 px-3.5 py-2">
                File-level changes were not captured for this session.
              </div>
            ) : (
              report.files.map((file, i) => {
                const statusStyle = fileStatusClasses[file.status] || {
                  text: "text-mc-text-3",
                  bg: "bg-mc-text-3/[0.09]",
                };
                return (
                  <div
                    key={i}
                    className={`flex items-center gap-2 px-3.5 py-[5px] ${
                      i < report.files.length - 1
                        ? "border-b border-mc-border-0"
                        : ""
                    }`}
                  >
                    <span
                      className={`text-[9px] font-bold font-mono px-[5px] py-[1px] rounded-[3px] ${statusStyle.text} ${statusStyle.bg}`}
                    >
                      {file.status}
                    </span>
                    <span className="text-[11px] font-mono text-mc-text-1 flex-1">
                      {file.path}
                    </span>
                    <span className="text-[10px] font-mono text-mc-text-3">
                      {file.lines}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </Section>

        {/* Roadmap Match */}
        {roadmapMatches.length > 0 && (
          <div className="px-3.5 py-2.5 rounded-lg bg-mc-green-muted border border-mc-green-border">
            <div className="text-[10px] font-bold font-mono text-mc-green uppercase tracking-[0.06em] mb-1">
              Roadmap Match Detected
            </div>
            {roadmapMatches.map((match, i) => (
              <div key={i} className="text-xs text-mc-text-1">
                ✓ {match}
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 mt-auto pt-3 border-t border-mc-border-0">
          <Button primary className="flex-1" onClick={onApprove}>
            <Icons.check size={10} /> Approve & Continue
          </Button>
          <Button className="flex-1" onClick={onRetry}>
            <Icons.retry size={10} /> Retry with Context
          </Button>
          <Button danger onClick={onRevert}>
            Revert
          </Button>
        </div>
      </div>
    </div>
  );
}
