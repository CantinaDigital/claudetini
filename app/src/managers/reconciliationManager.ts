import { create } from "zustand";
import { api } from "../api/backend";
import type {
  ReconciliationReport,
  ReconciliationFooterState,
} from "../types";

// Module-level polling interval (not in reactive state)
let pollInterval: ReturnType<typeof setInterval> | null = null;
let pollGeneration = 0; // Incremented on each new poll to detect stale callbacks

function clearPoll(): void {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

interface ReconciliationManagerState {
  footerState: ReconciliationFooterState;
  report: ReconciliationReport | null;
  jobId: string | null;
  showModal: boolean;
  checkedItems: Set<string>;

  // Actions
  check: (projectId: string, opts: { enabled: boolean }) => Promise<void>;
  analyze: (projectId: string, opts: { confidenceThreshold: number }) => Promise<void>;
  verifyProgress: (projectId: string, opts: { confidenceThreshold: number }) => Promise<void>;
  verifyProgressAI: (projectId: string, opts: { confidenceThreshold: number }) => Promise<void>;
  apply: (
    projectId: string,
    acceptedItems: string[],
    dismissedItems: string[]
  ) => Promise<void>;
  undo: (projectId: string) => Promise<number>;
  dismiss: () => void;
  openModal: () => void;
  closeModal: () => void;
  toggleCheckedItem: (text: string) => void;
  toggleAllHighConfidence: () => void;
  setFooterState: (state: ReconciliationFooterState) => void;
  cleanup: () => void;
}

export const useReconciliationManager = create<ReconciliationManagerState>(
  (set, get) => ({
    footerState: "hidden",
    report: null,
    jobId: null,
    showModal: false,
    checkedItems: new Set<string>(),

    check: async (projectId, { enabled }) => {
      if (!enabled) {
        console.log("Reconciliation is disabled in settings, skipping check");
        set({ footerState: "hidden" });
        return;
      }

      try {
        console.log("Checking for reconciliation changes...", projectId);
        const result = await api.quickCheckChanges(projectId);
        console.log("Quick check result:", result);

        if (result.has_changes) {
          set({ footerState: "changes_detected" });
        } else {
          set({ footerState: "hidden" });
        }
      } catch (error) {
        console.error("Failed to check for reconciliation:", error);
        set({ footerState: "hidden" });
      }
    },

    analyze: async (projectId, { confidenceThreshold }) => {
      try {
        console.log("Starting reconciliation analysis...");
        set({ footerState: "analyzing" });

        const result = await api.startReconciliationAnalysis(
          projectId,
          confidenceThreshold
        );
        console.log("Analysis started, job ID:", result.job_id);
        set({ jobId: result.job_id });

        // Start polling for reconciliation status
        pollReconciliationStatus(result.job_id, projectId);
      } catch (error) {
        console.error("Failed to start reconciliation analysis:", error);
        set({ footerState: "hidden" });
      }
    },

    verifyProgress: async (projectId, { confidenceThreshold }) => {
      try {
        console.log("Starting progress verification...");
        set({ footerState: "analyzing" });

        const result = await api.startProgressVerification(
          projectId,
          confidenceThreshold
        );
        console.log("Verification started, job ID:", result.job_id);
        set({ jobId: result.job_id });

        // Start polling with auto-show modal
        pollVerificationStatus(result.job_id, projectId);
      } catch (error) {
        console.error("Failed to start progress verification:", error);
        set({ footerState: "hidden" });
      }
    },

    verifyProgressAI: async (projectId, { confidenceThreshold }) => {
      try {
        console.log("Starting AI-powered progress verification...");
        set({ footerState: "analyzing" });

        const result = await api.startAIProgressVerification(
          projectId,
          confidenceThreshold
        );
        console.log("AI Verification started, job ID:", result.job_id);
        set({ jobId: result.job_id });

        // Start polling with auto-show modal
        pollVerificationStatus(result.job_id, projectId);
      } catch (error) {
        console.error("Failed to start AI progress verification:", error);
        set({ footerState: "hidden" });
        const { toast } = await import("../components/ui/Toast");
        toast.error(
          "AI Verification Failed",
          error instanceof Error ? error.message : "An error occurred"
        );
      }
    },

    apply: async (projectId, acceptedItems, dismissedItems) => {
      const { report } = get();

      if (!report) {
        console.warn("applyReconciliation: Missing report");
        return;
      }

      try {
        console.log("Applying reconciliation:", {
          acceptedItems,
          dismissedItems,
        });
        await api.applyReconciliation(projectId, {
          report_id: report.report_id,
          accepted_items: acceptedItems,
          dismissed_items: dismissedItems,
        });

        console.log(
          `Applied ${acceptedItems.length} suggestions, dismissed ${dismissedItems.length}`
        );

        // Refresh roadmap (fire-and-forget to update caches)
        await api.getRoadmap(projectId);

        set({
          footerState: "hidden",
          showModal: false,
          report: null,
        });
      } catch (error) {
        console.error("Failed to apply reconciliation:", error);
      }
    },

    undo: async (projectId) => {
      try {
        const result = await api.undoReconciliation(projectId);
        console.log(`Undid ${result.items_reverted} items`);

        // Refresh roadmap (fire-and-forget to update caches)
        await api.getRoadmap(projectId);

        return result.items_reverted;
      } catch (error) {
        console.error("Failed to undo reconciliation:", error);
        return 0;
      }
    },

    dismiss: () => {
      pollGeneration++; // Invalidate any in-flight poll callbacks
      clearPoll();
      set({
        footerState: "hidden",
        showModal: false,
        report: null,
        jobId: null,
      });
    },

    openModal: () => set({ showModal: true }),

    closeModal: () => set({ showModal: false }),

    toggleCheckedItem: (text) => {
      const { checkedItems } = get();
      const newSet = new Set(checkedItems);
      if (newSet.has(text)) {
        newSet.delete(text);
      } else {
        newSet.add(text);
      }
      set({ checkedItems: newSet });
    },

    toggleAllHighConfidence: () => {
      const { report, checkedItems } = get();
      if (!report) return;

      const highConfidence = report.suggestions.filter(
        (s) => s.confidence >= 0.9
      );
      const allChecked = highConfidence.every((s) =>
        checkedItems.has(s.item_text)
      );

      const newSet = new Set(checkedItems);
      if (allChecked) {
        highConfidence.forEach((s) => newSet.delete(s.item_text));
      } else {
        highConfidence.forEach((s) => newSet.add(s.item_text));
      }
      set({ checkedItems: newSet });
    },

    setFooterState: (state) => set({ footerState: state }),

    cleanup: () => {
      pollGeneration++; // Invalidate any in-flight poll callbacks
      clearPoll();
    },
  })
);

// -------------------------------------------------------
// Internal polling helpers (module-scoped, not in store)
// -------------------------------------------------------

function pollVerificationStatus(jobId: string, projectId: string): void {
  clearPoll();
  const gen = ++pollGeneration;

  pollInterval = setInterval(async () => {
    // Stale poll guard: if a new poll started, stop this one
    if (gen !== pollGeneration) return;

    try {
      const status = await api.getReconciliationJobStatus(projectId, jobId);
      if (gen !== pollGeneration) return; // Check again after async
      console.log("Verification poll status:", status);

      if (status.status === "complete") {
        clearPoll();

        const report = await api.getReconciliationResult(projectId, jobId);
        if (gen !== pollGeneration) return; // Check again after async
        console.log("Got verification report:", report);

        if (report.suggestions.length > 0) {
          useReconciliationManager.setState({
            report,
            footerState: "report_ready",
            showModal: true,
            checkedItems: new Set(report.suggestions.map((s) => s.item_text)),
          });
        } else {
          useReconciliationManager.setState({
            footerState: "no_matches",
          });
          const { toast } = await import("../components/ui/Toast");
          toast.info(
            "Verification Complete",
            "No additional completed items detected. Progress appears accurate."
          );
        }
      } else if (status.status === "failed") {
        clearPoll();
        useReconciliationManager.setState({ footerState: "hidden" });
        console.error("Verification failed:", status.error);
        const { toast } = await import("../components/ui/Toast");
        toast.error(
          "Verification Failed",
          status.error || "An error occurred"
        );
      }
    } catch (error) {
      clearPoll();
      useReconciliationManager.setState({ footerState: "hidden" });
      console.error("Failed to poll verification status:", error);
    }
  }, 2000);
}

function pollReconciliationStatus(jobId: string, projectId: string): void {
  clearPoll();
  const gen = ++pollGeneration;

  pollInterval = setInterval(async () => {
    // Stale poll guard: if a new poll started, stop this one
    if (gen !== pollGeneration) return;

    try {
      const status = await api.getReconciliationJobStatus(projectId, jobId);
      if (gen !== pollGeneration) return; // Check again after async
      console.log("Poll status:", status);

      if (status.status === "complete") {
        clearPoll();

        const report = await api.getReconciliationResult(projectId, jobId);
        if (gen !== pollGeneration) return; // Check again after async
        console.log("Got report:", report);

        if (!report.old_snapshot_id || report.old_snapshot_id === "") {
          useReconciliationManager.setState({
            footerState: "baseline_created",
          });
        } else if (report.suggestions.length > 0) {
          useReconciliationManager.setState({
            report,
            footerState: "report_ready",
            checkedItems: new Set(report.suggestions.map((s) => s.item_text)),
          });
        } else {
          useReconciliationManager.setState({
            footerState: "no_matches",
          });
        }
      } else if (status.status === "failed") {
        clearPoll();
        useReconciliationManager.setState({ footerState: "hidden" });
        console.error("Reconciliation analysis failed:", status.error);
      }
    } catch (error) {
      clearPoll();
      useReconciliationManager.setState({ footerState: "hidden" });
      console.error("Failed to poll reconciliation status:", error);
    }
  }, 2000);
}
