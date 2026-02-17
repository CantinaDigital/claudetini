import { useEffect } from "react";
import { useReconciliationManager } from "../../managers/reconciliationManager";
import { useSettingsStore } from "../../stores/settingsStore";
import { Button } from "../ui/Button";

interface ReconciliationFooterProps {
  projectPath: string;
}

/**
 * Unobtrusive footer notification for reconciliation workflow.
 */
export function ReconciliationFooter({ projectPath }: ReconciliationFooterProps) {
  const footerState = useReconciliationManager((s) => s.footerState);
  const report = useReconciliationManager((s) => s.report);
  const analyze = useReconciliationManager((s) => s.analyze);
  const dismiss = useReconciliationManager((s) => s.dismiss);
  const openModal = useReconciliationManager((s) => s.openModal);
  const confidenceThreshold = useSettingsStore((s) => s.reconciliationConfidenceThreshold);

  useEffect(() => {
    if (footerState === "no_matches" || footerState === "baseline_created") {
      const AUTO_DISMISS_MS = 10_000;
      const timer = setTimeout(() => dismiss(), AUTO_DISMISS_MS);
      return () => clearTimeout(timer);
    }
  }, [footerState, dismiss]);

  if (footerState === "hidden") return null;

  const handleAnalyze = () => analyze(projectPath, { confidenceThreshold });
  const handleViewReport = () => openModal();
  const handleDismiss = () => dismiss();

  return (
    <div className="fixed bottom-0 left-0 right-0 h-12 bg-mc-surface-1 border-t border-mc-border-1 flex items-center justify-between px-5 z-50 font-sans text-[13px] animate-slide-up">
      <div className="flex items-center gap-3">
        {footerState === "changes_detected" && (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-mc-cyan" />
            <span className="text-mc-text-1">
              Changes detected - Ready to analyze for roadmap updates
            </span>
          </>
        )}

        {footerState === "analyzing" && (
          <>
            <div className="w-4 h-4 border-2 border-mc-border-2 border-t-mc-accent rounded-full animate-spin" />
            <span className="text-mc-text-1">
              Analyzing changes... (this may take 30-60 seconds)
            </span>
          </>
        )}

        {footerState === "report_ready" && (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-mc-green animate-pulse" />
            <span className="text-mc-text-1">
              Progress verification complete -{" "}
              <strong>{report?.suggestions.length || 0} potentially completed items found</strong> (click "View Report" or "Dismiss")
            </span>
          </>
        )}

        {footerState === "no_matches" && (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-mc-text-3" />
            <span className="text-mc-text-2">
              Analysis complete - No high-confidence matches found
            </span>
          </>
        )}

        {footerState === "baseline_created" && (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-mc-cyan" />
            <span className="text-mc-text-2">
              Baseline snapshot created - Make more changes and run analysis again to see suggestions
            </span>
          </>
        )}
      </div>

      <div className="flex gap-2">
        {footerState === "changes_detected" && (
          <>
            <Button onClick={handleAnalyze} primary>Analyze for Reconciliation</Button>
            <Button onClick={handleDismiss}>Dismiss</Button>
          </>
        )}

        {footerState === "analyzing" && (
          <span className="text-mc-text-3 text-xs">Running background analysis...</span>
        )}

        {footerState === "report_ready" && (
          <>
            <Button onClick={handleViewReport} primary>View Report</Button>
            <Button onClick={handleDismiss}>Dismiss</Button>
          </>
        )}

        {(footerState === "no_matches" || footerState === "baseline_created") && (
          <Button onClick={handleDismiss}>Dismiss</Button>
        )}
      </div>
    </div>
  );
}
