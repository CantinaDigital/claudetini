import { useMemo, useEffect, useRef } from "react";
import { useReconciliationManager } from "../../managers/reconciliationManager";
import { toast } from "../ui/Toast";
import { Button } from "../ui/Button";
import { SuggestionCard } from "./SuggestionCard";

interface ReconciliationModalProps {
  projectPath: string;
}

export function ReconciliationModal({ projectPath }: ReconciliationModalProps) {
  const report = useReconciliationManager((s) => s.report);
  const showModal = useReconciliationManager((s) => s.showModal);
  const checkedItems = useReconciliationManager((s) => s.checkedItems);
  const apply = useReconciliationManager((s) => s.apply);
  const dismiss = useReconciliationManager((s) => s.dismiss);
  const closeModal = useReconciliationManager((s) => s.closeModal);
  const toggleCheckedItem = useReconciliationManager((s) => s.toggleCheckedItem);
  const toggleAllHighConfidence = useReconciliationManager((s) => s.toggleAllHighConfidence);

  // Track checkedItems via ref to avoid re-registering keyboard handler on every check toggle
  const checkedItemsRef = useRef(checkedItems);
  checkedItemsRef.current = checkedItems;

  // Calculate stats (MUST be before early return to follow Rules of Hooks)
  const changeSummary = useMemo(() => {
    if (!report) {
      return {
        files: "No file changes",
        filesCreated: 0,
        filesModified: 0,
        filesDeleted: 0,
        linesAdded: 0,
        linesRemoved: 0,
        totalLoc: 0,
        commits: "0 commits",
      };
    }

    const filesCreated = report.files_changed.filter(
      (f) => f.change_type === "added"
    ).length;
    const filesModified = report.files_changed.filter(
      (f) => f.change_type === "modified"
    ).length;
    const filesDeleted = report.files_changed.filter(
      (f) => f.change_type === "deleted"
    ).length;

    const linesAdded = report.files_changed
      .filter((f) => f.loc_delta > 0)
      .reduce((sum, f) => sum + f.loc_delta, 0);

    const linesRemoved = Math.abs(
      report.files_changed
        .filter((f) => f.loc_delta < 0)
        .reduce((sum, f) => sum + f.loc_delta, 0)
    );

    const totalLoc = linesAdded - linesRemoved;
    const commits = report.commits_added;

    const parts = [];
    if (filesCreated > 0) parts.push(`${filesCreated} created`);
    if (filesModified > 0) parts.push(`${filesModified} modified`);
    if (filesDeleted > 0) parts.push(`${filesDeleted} deleted`);

    return {
      files: parts.join(", ") || "No file changes",
      filesCreated,
      filesModified,
      filesDeleted,
      linesAdded,
      linesRemoved,
      totalLoc,
      commits: `${commits} commit${commits !== 1 ? "s" : ""}`,
    };
  }, [report]);

  const handleApply = async () => {
    if (!report) return;
    const currentChecked = checkedItemsRef.current;
    const acceptedItems = Array.from(currentChecked);
    const dismissedItems = report.suggestions
      .filter((s) => !currentChecked.has(s.item_text))
      .map((s) => s.item_text);

    await apply(projectPath, acceptedItems, dismissedItems);

    if (acceptedItems.length > 0) {
      toast.success(
        "Roadmap Updated",
        `Marked ${acceptedItems.length} item${acceptedItems.length > 1 ? "s" : ""} complete`
      );
    }

    if (dismissedItems.length > 0) {
      toast.info(
        "Suggestions Dismissed",
        `Dismissed ${dismissedItems.length} suggestion${dismissedItems.length > 1 ? "s" : ""}`
      );
    }
  };

  const handleSkip = () => {
    closeModal();
  };

  const handleDismiss = () => {
    dismiss();
  };

  // Keyboard shortcuts
  useEffect(() => {
    if (!showModal) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleSkip();
        return;
      }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        handleApply();
        return;
      }
      if (e.key === "a" && !e.metaKey && !e.ctrlKey) {
        toggleAllHighConfidence();
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showModal]);

  if (!showModal || !report) {
    return null;
  }

  const highConfidenceCount = report.suggestions.filter(
    (s) => s.confidence >= 0.9
  ).length;

  const addedBarPct = Math.min(
    100,
    (changeSummary.linesAdded /
      (changeSummary.linesAdded + changeSummary.linesRemoved)) *
      100
  );

  const removedBarPct = Math.min(
    100,
    (changeSummary.linesRemoved /
      (changeSummary.linesAdded + changeSummary.linesRemoved)) *
      100
  );

  return (
    <div
      className="fixed inset-0 bg-black/70 z-[100] flex items-center justify-center animate-fade-in-fast"
      onClick={handleSkip}
    >
      <div
        className="w-[680px] max-h-[90vh] bg-mc-surface-1 rounded-[14px] border border-mc-border-1 animate-scale-in overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-5 border-b border-mc-border-1">
          <div className="text-[16px] font-bold text-mc-text-0 mb-1">
            Roadmap Updates Available
          </div>
          <div className="text-xs text-mc-text-3">
            Review and apply suggested completions based on recent changes
          </div>
        </div>

        {/* Change summary with LOC visualization */}
        <div className="px-6 py-3.5 bg-mc-surface-0 border-b border-mc-border-0">
          <div className="flex gap-4 items-center text-xs text-mc-text-2 mb-3">
            <div>{changeSummary.files}</div>
            <div>•</div>
            <div>{changeSummary.commits}</div>
          </div>

          {/* LOC bar chart */}
          {(changeSummary.linesAdded > 0 || changeSummary.linesRemoved > 0) && (
            <div className="flex flex-col gap-1.5">
              {/* Lines added */}
              {changeSummary.linesAdded > 0 && (
                <div className="flex items-center gap-2">
                  <div className="text-[10px] text-mc-text-3 w-[50px] text-right">
                    +{changeSummary.linesAdded}
                  </div>
                  <div
                    className="flex-1 h-4 bg-mc-green-muted border border-mc-green-border rounded-[3px] relative overflow-hidden"
                  >
                    <div
                      className="absolute left-0 top-0 bottom-0 bg-mc-green opacity-50"
                      style={{ width: `${addedBarPct}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Lines removed */}
              {changeSummary.linesRemoved > 0 && (
                <div className="flex items-center gap-2">
                  <div className="text-[10px] text-mc-text-3 w-[50px] text-right">
                    -{changeSummary.linesRemoved}
                  </div>
                  <div
                    className="flex-1 h-4 bg-mc-red-muted border border-mc-red-border rounded-[3px] relative overflow-hidden"
                  >
                    <div
                      className="absolute left-0 top-0 bottom-0 bg-mc-red opacity-50"
                      style={{ width: `${removedBarPct}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Net change */}
              <div className="text-[10px] text-mc-text-3 text-right font-mono">
                Net: {changeSummary.totalLoc > 0 ? "+" : ""}
                {changeSummary.totalLoc} lines
              </div>
            </div>
          )}
        </div>

        {/* Bulk actions */}
        {highConfidenceCount > 0 && (
          <div className="px-6 py-3 border-b border-mc-border-0 flex items-center justify-between">
            <span className="text-xs text-mc-text-2">
              {highConfidenceCount} high-confidence suggestion
              {highConfidenceCount > 1 ? "s" : ""}
            </span>
            <button
              onClick={toggleAllHighConfidence}
              className="bg-transparent border border-mc-border-2 rounded-[6px] px-2.5 py-1 font-sans text-[11px] font-semibold text-mc-text-2 cursor-pointer"
            >
              Toggle all high-confidence
            </button>
          </div>
        )}

        {/* Suggestions list */}
        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          {report.suggestions.map((suggestion) => (
            <SuggestionCard
              key={suggestion.item_text}
              suggestion={suggestion}
              checked={checkedItems.has(suggestion.item_text)}
              onToggle={() => toggleCheckedItem(suggestion.item_text)}
              projectId={projectPath}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 border-t border-mc-border-1 flex justify-between items-center">
          <div className="flex flex-col gap-1">
            <div className="flex gap-2">
              <Button onClick={handleSkip}>Close (Keep Notification)</Button>
              <Button onClick={handleDismiss}>Dismiss Completely</Button>
            </div>
            <div className="text-[10px] text-mc-text-3 font-mono">
              Esc: Close • ⌘Enter: Apply • A: Toggle high-confidence
            </div>
          </div>

          <Button onClick={handleApply} primary>
            Update Roadmap ({checkedItems.size})
          </Button>
        </div>
      </div>
    </div>
  );
}
