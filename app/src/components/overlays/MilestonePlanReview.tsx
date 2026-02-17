import { useEffect, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import { useDispatchManager } from "../../managers/dispatchManager";
import type { MilestoneItem } from "../../types";

interface MilestonePlanReviewProps {
  milestoneTitle: string;
  remainingItems: MilestoneItem[];
  planOutput: string;
  isPlanning: boolean;
  onExecute: (mode: string, userNotes?: string) => void;
  onCancel: () => void;
}

const MODES = [
  { key: "standard", label: "Standard", desc: "Default execution mode" },
  { key: "blitz", label: "Blitz", desc: "Fast, minimal verification" },
  { key: "with-review", label: "With Review", desc: "Agent-based with review" },
] as const;

function secondsToDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function MilestonePlanReview({
  milestoneTitle,
  remainingItems,
  planOutput,
  isPlanning,
  onExecute,
  onCancel,
}: MilestonePlanReviewProps) {
  const [selectedMode, setSelectedMode] = useState("standard");
  const [userNotes, setUserNotes] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const outputRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Subscribe to live dispatch state
  const isDispatching = useDispatchManager((s) => s.isDispatching);
  const isStreaming = useDispatchManager((s) => s.isStreaming);
  const streamOutputLines = useDispatchManager((s) => s.streamOutputLines);
  const outputTail = useDispatchManager((s) => s.outputTail);
  const statusText = useDispatchManager((s) => s.statusText);
  const elapsedSeconds = useDispatchManager((s) => s.elapsedSeconds);
  const progressPct = useDispatchManager((s) => s.progressPct);
  const cancelAction = useDispatchManager((s) => s.cancel);
  const dispatchFailed = useDispatchManager((s) => s.dispatchFailed);
  const errorDetail = useDispatchManager((s) => s.errorDetail);

  // Live output lines — prefer streaming, fall back to outputTail
  const liveLines = isStreaming && streamOutputLines.length > 0
    ? streamOutputLines
    : outputTail
      ? outputTail.split("\n")
      : [];

  // Auto-scroll the live output area
  useEffect(() => {
    if (autoScroll && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [liveLines, autoScroll]);

  const handleScroll = () => {
    if (!outputRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = outputRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 30;
    setAutoScroll(isAtBottom);
  };

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await cancelAction();
    } finally {
      setIsCancelling(false);
      onCancel();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-[9999] flex items-center justify-center">
      <div
        className="w-[680px] max-h-[90vh] flex flex-col bg-mc-surface-1 rounded-[14px] border border-mc-border-1 animate-[fadeIn_0.2s_ease] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-mc-border-0 shrink-0 flex items-center gap-2.5">
          {isPlanning && isDispatching && (
            <span className="w-3.5 h-3.5 rounded-full border-2 border-mc-border-1 border-t-mc-accent animate-[cc-spin_0.9s_linear_infinite] inline-block shrink-0" />
          )}
          {!isPlanning && (
            <span className="text-mc-green text-sm shrink-0">
              <Icons.check size={14} color={t.green} />
            </span>
          )}
          <div className="flex-1">
            <div className="text-[15px] font-bold text-mc-text-0">
              {isPlanning ? "Planning Milestone..." : "Plan Ready — Review & Execute"}
            </div>
            <div className="text-[11px] text-mc-text-3 mt-px">
              {milestoneTitle} · {remainingItems.length} tasks
              {isPlanning && elapsedSeconds > 0 && (
                <> · {secondsToDuration(elapsedSeconds)}</>
              )}
            </div>
          </div>
        </div>

        {/* Progress bar (planning only) */}
        {isPlanning && (
          <div className="h-[3px] bg-mc-surface-3 shrink-0">
            <div
              className={`h-full transition-[width] duration-[250ms] ease ${
                dispatchFailed ? "bg-mc-red" : "bg-mc-accent"
              }`}
              style={{ width: `${Math.max(3, Math.min(100, progressPct))}%` }}
            />
          </div>
        )}

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Tasks list (always visible, compact) */}
          <div className="px-5 py-2.5 border-b border-mc-border-0">
            <div className="mc-label mb-1.5 tracking-[0.06em]">
              Tasks ({remainingItems.length})
            </div>
            <div className="flex flex-wrap gap-y-[3px] gap-x-3">
              {remainingItems.map((item, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 text-[11px] text-mc-text-2"
                >
                  <div className="w-3 h-3 rounded-[3px] border-[1.5px] border-mc-border-2 shrink-0" />
                  <span className="max-w-[280px] overflow-hidden text-ellipsis whitespace-nowrap">
                    {item.text}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* ===== PLANNING PHASE: Live terminal output ===== */}
          {isPlanning && (
            <div className="px-5 py-2.5">
              <div className="flex items-center justify-between px-2.5 py-1.5 bg-mc-surface-2 rounded-t-lg border-b border-mc-border-0">
                <div className="text-[9px] text-mc-text-3 uppercase tracking-[0.5px] flex items-center gap-1.5 font-bold">
                  {isDispatching && (
                    <span className="w-1.5 h-1.5 rounded-full bg-mc-green animate-[cc-pulse_1.5s_infinite]" />
                  )}
                  Claude Code Output
                  {liveLines.length > 0 && (
                    <span className="text-mc-text-3 font-normal">
                      ({liveLines.length} lines)
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-mc-text-3">
                  {statusText || "Waiting for output..."}
                </div>
              </div>
              <div
                ref={outputRef}
                onScroll={handleScroll}
                className="font-mono text-[10.5px] leading-[1.5] text-mc-text-2 bg-mc-bg border border-mc-border-0 border-t-0 rounded-b-lg px-3 py-2.5 text-left whitespace-pre-wrap break-words min-h-[200px] max-h-[380px] overflow-y-auto"
              >
                {liveLines.length > 0 ? (
                  liveLines.map((line, i) => (
                    <div key={i} className="min-h-[1.5em]">
                      {line || " "}
                    </div>
                  ))
                ) : (
                  <div className="flex items-center gap-2 text-mc-text-3">
                    <span className="w-1.5 h-1.5 rounded-full bg-mc-accent animate-[cc-pulse_1.5s_infinite] shrink-0" />
                    {statusText || "Initializing Claude Code..."}
                  </div>
                )}
                {isDispatching && isStreaming && (
                  <span className="inline-block w-1.5 h-3 bg-mc-accent animate-[cc-blink_1s_step-end_infinite] ml-0.5 align-middle" />
                )}
              </div>

              {/* Error state during planning */}
              {dispatchFailed && errorDetail && (
                <div className="text-[11px] text-mc-red bg-mc-red-muted border border-mc-red-border rounded-lg px-2.5 py-2 mt-2 whitespace-pre-wrap max-h-[120px] overflow-y-auto">
                  {errorDetail}
                </div>
              )}
            </div>
          )}

          {/* ===== REVIEWING PHASE: Completed plan + review controls ===== */}
          {!isPlanning && (
            <>
              {/* Plan output */}
              <div className="px-5 py-2.5 border-b border-mc-border-0">
                <div className="mc-label mb-1.5 tracking-[0.06em]">
                  Plan Output
                </div>
                <pre className="text-[10.5px] font-mono text-mc-text-2 leading-[1.6] whitespace-pre-wrap break-words m-0 bg-mc-bg border border-mc-border-0 rounded-lg p-3 max-h-[300px] overflow-y-auto">
                  {planOutput || "(No plan output received)"}
                </pre>
              </div>

              {/* User notes */}
              <div className="px-5 py-2.5 border-b border-mc-border-0">
                <div className="mc-label mb-1.5 tracking-[0.06em]">
                  Notes (optional)
                </div>
                <textarea
                  value={userNotes}
                  onChange={(e) => setUserNotes(e.target.value)}
                  placeholder="Add context, answer questions from the plan, or adjust the approach..."
                  className="w-full min-h-[50px] text-xs text-mc-text-1 leading-[1.5] font-mono bg-mc-surface-0 border border-mc-border-1 rounded-md p-2.5 resize-y outline-none"
                />
              </div>

              {/* Mode selector */}
              <div className="px-5 py-2.5">
                <div className="mc-label mb-1.5 tracking-[0.06em]">
                  Execution Mode
                </div>
                <div className="flex gap-1.5">
                  {MODES.map((m) => (
                    <button
                      key={m.key}
                      onClick={() => setSelectedMode(m.key)}
                      className={`flex-1 p-2 px-2.5 rounded-lg text-left cursor-pointer ${
                        selectedMode === m.key
                          ? "border-[1.5px] border-mc-accent bg-mc-accent-muted"
                          : "border border-mc-border-1 bg-mc-surface-0"
                      }`}
                    >
                      <div
                        className={`text-xs font-semibold ${
                          selectedMode === m.key ? "text-mc-accent" : "text-mc-text-1"
                        }`}
                      >
                        {m.label}
                      </div>
                      <div className="text-[10px] text-mc-text-3 mt-0.5">
                        {m.desc}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex gap-2 px-5 py-3 border-t border-mc-border-0 shrink-0">
          {isPlanning ? (
            <>
              <Button
                small
                onClick={handleCancel}
                className={`text-mc-red border-mc-red ${isCancelling ? "opacity-60" : ""}`}
              >
                {isCancelling ? "Cancelling..." : "Cancel"}
              </Button>
              <div className="flex-1" />
              <div className="text-[11px] text-mc-text-3 flex items-center">
                {isDispatching
                  ? "Claude Code is analyzing the codebase..."
                  : dispatchFailed
                    ? "Planning failed. Cancel and retry."
                    : ""}
              </div>
            </>
          ) : (
            <>
              <Button small onClick={onCancel}>
                Cancel
              </Button>
              <div className="flex-1" />
              <Button
                primary
                onClick={() =>
                  onExecute(selectedMode, userNotes.trim() || undefined)
                }
              >
                <Icons.play size={10} /> Execute ({remainingItems.length} tasks)
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
