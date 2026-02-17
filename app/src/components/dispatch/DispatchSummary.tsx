import { useState } from "react";
import { Button } from "../ui/Button";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { DiffBlock, looksLikeDiff } from "../ui/DiffBlock";

interface FileChange {
  file: string;
  lines_added: number;
  lines_removed: number;
  status: string;
}

interface DispatchSummaryProps {
  success: boolean;
  filesChanged: FileChange[];
  totalAdded: number;
  totalRemoved: number;
  summaryMessage: string | null;
  hasErrors: boolean;
  onReviewChanges: () => void;
  onMarkComplete: () => void;
  onCommit: () => void;
  onClose: () => void;
  // Claude Code output tail (shown when errors exist)
  outputTail?: string | null;
}

export function DispatchSummary({
  success,
  filesChanged,
  totalAdded,
  totalRemoved,
  summaryMessage,
  hasErrors,
  onReviewChanges,
  onMarkComplete,
  onCommit,
  onClose,
  outputTail,
}: DispatchSummaryProps) {
  const [showOutput, setShowOutput] = useState(false);

  const headerTitle = success
    ? "Task Completed"
    : hasErrors
      ? "Task Completed with Errors"
      : "Task Ended";

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-[9999]"
      onClick={onClose}
    >
      <div
        className="bg-mc-surface-1 rounded-xl px-7 py-6 border border-mc-border-1 w-[580px] max-w-[90vw] max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-2xl">
            {success ? "✓" : hasErrors ? "⚠" : "ℹ"}
          </span>
          <div className="flex-1">
            <div className="text-lg font-bold text-mc-text-0">
              {headerTitle}
            </div>
            {summaryMessage && (
              <div className="text-[11px] text-mc-text-3 mt-1">
                <InlineMarkdown>{summaryMessage}</InlineMarkdown>
              </div>
            )}
          </div>
        </div>

        {/* Error output (when hasErrors and we have output) */}
        {hasErrors && outputTail && (
          <div className="mb-4">
            <button
              onClick={() => setShowOutput((v) => !v)}
              className="flex items-center gap-1.5 text-[10px] font-bold font-mono text-mc-amber uppercase tracking-[0.06em] mb-1.5 bg-transparent border-none cursor-pointer p-0"
            >
              {showOutput ? "▾" : "▸"} Claude Code Output (errors)
            </button>
            {showOutput && (
              outputTail && looksLikeDiff(outputTail) ? (
                <DiffBlock text={outputTail} maxHeight={200} />
              ) : (
                <pre className="text-[10.5px] font-mono text-mc-text-2 leading-normal whitespace-pre-wrap break-words m-0 bg-mc-bg border border-mc-border-0 rounded-lg p-3 max-h-[200px] overflow-y-auto">
                  {outputTail}
                </pre>
              )
            )}
          </div>
        )}

        {/* Stats */}
        {filesChanged.length > 0 && (
          <div className="flex gap-5 px-4 py-3 bg-mc-surface-2 rounded-lg mb-4">
            <div>
              <div className="text-[10px] text-mc-text-3 uppercase">
                Files Changed
              </div>
              <div className="text-xl font-bold text-mc-text-0">
                {filesChanged.length}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-mc-text-3 uppercase">
                Lines Added
              </div>
              <div className="text-xl font-bold text-mc-green">
                +{totalAdded}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-mc-text-3 uppercase">
                Lines Removed
              </div>
              <div className="text-xl font-bold text-mc-red">
                -{totalRemoved}
              </div>
            </div>
          </div>
        )}

        {/* File list */}
        {filesChanged.length > 0 && (
          <div className="mb-4 max-h-[200px] overflow-y-auto bg-mc-surface-0 border border-mc-border-0 rounded-lg px-3 py-2">
            <div className="text-[9px] text-mc-text-3 uppercase font-bold mb-1.5">
              Files Changed
            </div>
            {filesChanged.map((file, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-1 text-[11px] font-mono"
              >
                <span className="text-mc-text-1 flex-1 mr-2.5">{file.file}</span>
                <span className="text-mc-text-3 shrink-0">
                  <span className="text-mc-green">+{file.lines_added}</span>
                  {" "}
                  <span className="text-mc-red">-{file.lines_removed}</span>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* No changes message */}
        {filesChanged.length === 0 && (
          <div className="p-4 text-center text-mc-text-3 text-xs mb-4">
            No files were changed during this execution.
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            {filesChanged.length > 0 && (
              <>
                <Button primary onClick={onReviewChanges} className="flex-1">
                  Review Changes
                </Button>
                {success && (
                  <Button onClick={onMarkComplete} className="flex-1">
                    Mark Task Complete
                  </Button>
                )}
              </>
            )}
            {filesChanged.length === 0 && (
              <Button onClick={onClose} className="flex-1">
                Close
              </Button>
            )}
          </div>

          {filesChanged.length > 0 && (
            <div className="flex gap-2">
              <Button onClick={onCommit} className="flex-1">
                Commit Changes
              </Button>
              <Button onClick={onClose} className="flex-1">
                Close
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
