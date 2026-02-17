import { Component, useEffect, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { TabBar } from "./components/layout/TabBar";
import { Dashboard } from "./components/layout/Dashboard";
import { OverviewTab } from "./components/overview/OverviewTab";
import { RoadmapTab } from "./components/roadmap/RoadmapTab";
import { GitTab } from "./components/git/GitTab";
import { TimelineTab } from "./components/timeline/TimelineTab";
import { GatesTab } from "./components/gates/GatesTab";
import IntelligenceTab from "./components/intelligence/IntelligenceTab";
import { ProductMapTab } from "./components/product-map/ProductMapTab";
import { LogsTab } from "./components/logs/LogsTab";
import { SettingsTab } from "./components/settings/SettingsTab";
import { FallbackModal } from "./components/dispatch/FallbackModal";
import { DispatchOverlay } from "./components/dispatch/DispatchOverlay";
import { DispatchMinimized } from "./components/dispatch/DispatchMinimized";
import { DispatchSummary } from "./components/dispatch/DispatchSummary";
import {
  SessionReportOverlay,
  type SessionReport,
} from "./components/overlays/SessionReportOverlay";
import {
  PreFlightInterstitial,
  generatePreFlightChecks,
  type PreFlightCheck,
} from "./components/overlays/PreFlightInterstitial";
import { ConfirmDialog } from "./components/ui/ConfirmDialog";
import { ToastContainer, toast, useToasts } from "./components/ui/Toast";
import { ReconciliationFooter } from "./components/footer/ReconciliationFooter";
import { ReconciliationModal } from "./components/roadmap/ReconciliationModal";
import { initBackend, isBackendConnected, api } from "./api/backend";
import { MilestonePlanReview } from "./components/overlays/MilestonePlanReview";
import type { Milestone, MilestoneItem, Status, TimelineEntry } from "./types";
import { useSettingsStore } from "./stores/settingsStore";
import { useDispatchManager, type DispatchContext } from "./managers/dispatchManager";
import { useReconciliationManager } from "./managers/reconciliationManager";
import { useProjectManager } from "./managers/projectManager";
import { useParallelManager } from "./managers/parallelManager";
import { ParallelExecutionOverlay } from "./components/roadmap/ParallelExecutionOverlay";

const TABS = ["Overview", "Roadmap", "Timeline", "Git", "Intelligence", "Product Map", "Quality Gates", "Logs", "Settings"];

/**
 * Global error boundary — prevents any component crash from producing a black screen.
 * Shows a recoverable error message with a retry button instead.
 */
class TabErrorBoundary extends Component<
  { tabName: string; children: ReactNode },
  { hasError: boolean; errorMsg: string }
> {
  constructor(props: { tabName: string; children: ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMsg: "" };
  }

  static getDerivedStateFromError(error: Error): { hasError: boolean; errorMsg: string } {
    return { hasError: true, errorMsg: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.tabName}] Render error:`, error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 p-10">
          <div className="text-sm text-mc-text-0 font-semibold">
            {this.props.tabName} encountered an error
          </div>
          <div className="text-[11px] text-mc-text-3 max-w-[400px] text-center">
            {this.state.errorMsg}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, errorMsg: "" })}
            className="border border-mc-accent-border rounded-md bg-mc-accent-muted text-mc-text-0 text-[11px] py-1.5 px-4 cursor-pointer mt-1"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function minutesToDuration(minutes: number): string {
  if (minutes >= 60) {
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }
  return `${minutes}m`;
}

function normalizeGateStatus(raw: string): Status {
  if (raw === "pass" || raw === "warn" || raw === "fail") return raw;
  return "warn";
}

function derivePreviousSessionStatus(entry?: TimelineEntry): Status | null {
  if (!entry) return null;
  const statuses = Object.values(entry.gateStatuses || {}).map(normalizeGateStatus);
  if (statuses.length === 0) return null;
  if (statuses.includes("fail")) return "fail";
  if (statuses.includes("warn")) return "warn";
  return "pass";
}

export default function App() {
  // Core app state
  const [activeTab, setActiveTab] = useState(0);
  const [initialized, setInitialized] = useState(false);
  const [backendConnected, setBackendConnected] = useState(false);
  const activeProjectPath = useProjectManager((s) => s.currentProject?.path) ?? "";

  // Overlay state
  const [showReport, setShowReport] = useState(false);
  const [selectedReport, setSelectedReport] = useState<SessionReport | null>(null);
  const [showPreflight, setShowPreflight] = useState(false);
  const [preFlightChecks, setPreFlightChecks] = useState<PreFlightCheck[]>([]);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmConfig, setConfirmConfig] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null>(null);
  const [showDispatchSummary, setShowDispatchSummary] = useState(false);
  const [dispatchSummary, setDispatchSummary] = useState<any>(null);

  // Dispatch manager
  const dispatchContext = useDispatchManager((s) => s.context);
  const setDispatchContext = useDispatchManager((s) => s.setContext);
  const showFallbackModal = useDispatchManager((s) => s.showFallbackModal);
  const fallbackPrompt = useDispatchManager((s) => s.fallbackPrompt);
  const isFallbackRunning = useDispatchManager((s) => s.isFallbackRunning);
  const fallbackProvider = useDispatchManager((s) => s.fallbackProvider);
  const fallbackOutput = useDispatchManager((s) => s.fallbackOutput);
  const fallbackError = useDispatchManager((s) => s.fallbackError);
  const fallbackErrorCode = useDispatchManager((s) => s.fallbackErrorCode);
  const fallbackStatusText = useDispatchManager((s) => s.fallbackStatusText);
  const fallbackPhase = useDispatchManager((s) => s.fallbackPhase);
  const executeDispatch = useDispatchManager((s) => s.execute);
  const retryDispatch = useDispatchManager((s) => s.retry);
  const runFallbackAction = useDispatchManager((s) => s.runFallback);
  const closeFallback = useDispatchManager((s) => s.closeFallback);

  // Milestone plan state
  const milestonePlanPhase = useDispatchManager((s) => s.milestonePlanPhase);
  const milestonePlanContext = useDispatchManager((s) => s.milestonePlanContext);
  const milestonePlanOutput = useDispatchManager((s) => s.milestonePlanOutput);
  const executeMilestone = useDispatchManager((s) => s.executeMilestone);
  const resetMilestonePlan = useDispatchManager((s) => s.resetMilestonePlan);

  const preSessionHooks = useSettingsStore((s) => s.preSessionHooks);
  const preferredFallback = useSettingsStore((s) => s.preferredFallback);

  const { toasts, dismiss: dismissToast } = useToasts();

  // Reconciliation manager
  const reconciliationCheck = useReconciliationManager((s) => s.check);
  const reconciliationEnabled = useSettingsStore((s) => s.reconciliationEnabled);

  // Backend initialization — skip if AppRouter already connected
  useEffect(() => {
    if (isBackendConnected()) {
      setBackendConnected(true);
      setInitialized(true);
      return;
    }
    const init = async () => {
      try {
        await initBackend();
        setBackendConnected(isBackendConnected());
      } catch (error) {
        console.error("Backend init failed:", error);
      } finally {
        setInitialized(true);
      }
    };
    void init();
  }, []);

  // Cleanup manager resources on unmount (timers, EventSources, polling)
  useEffect(() => {
    return () => {
      useDispatchManager.getState().cleanup();
      useReconciliationManager.getState().cleanup();
      useParallelManager.getState().cleanup();
    };
  }, []);

  // Check for reconciliation when backend connects
  useEffect(() => {
    if (backendConnected && activeProjectPath) {
      console.log("App: Checking for reconciliation on", activeProjectPath);
      reconciliationCheck(activeProjectPath, { enabled: reconciliationEnabled });
    }
  }, [backendConnected, activeProjectPath, reconciliationCheck, reconciliationEnabled]);

  // Show dispatch summary when dispatch completes successfully
  const isDispatching = useDispatchManager((s) => s.isDispatching);
  const dispatchFailed = useDispatchManager((s) => s.dispatchFailed);
  const dispatchJobId = useDispatchManager((s) => s.jobId);
  const dispatchLogFile = useDispatchManager((s) => s.logFile);
  const lastDispatchContext = useDispatchManager((s) => s.lastContext);
  const dispatchOutputTail = useDispatchManager((s) => s.outputTail);

  useEffect(() => {
    // Only show summary if dispatch just completed successfully (not failed)
    if (!isDispatching && !dispatchFailed && dispatchJobId && activeProjectPath) {
      // Skip summary for planning-phase dispatches — the plan review overlay handles this.
      // When a planning dispatch completes, milestonePlanPhase transitions to "reviewing"
      // before completeDispatch() fires. We don't want to show DispatchSummary for the plan.
      const currentPlanPhase = useDispatchManager.getState().milestonePlanPhase;
      if (currentPlanPhase === "reviewing") {
        return;
      }

      const fetchSummary = async () => {
        let summary: typeof dispatchSummary = null;
        try {
          summary = await api.getDispatchSummary(dispatchJobId, activeProjectPath, dispatchLogFile);
          setDispatchSummary(summary);
          setShowDispatchSummary(true);
        } catch (error) {
          console.error("Failed to get dispatch summary:", error);
        }

        // Batch mark-done for milestone plan execution
        const planPhase = useDispatchManager.getState().milestonePlanPhase;
        const planCtx = useDispatchManager.getState().milestonePlanContext;
        if (planPhase === "executing" && planCtx) {
          // Always mark items done when milestone execution dispatch completes.
          // The dispatch itself succeeded (Claude exited 0). Trust the result.
          try {
            const itemTexts = planCtx.remainingItems.map((i) => i.text);
            const result = await api.batchToggleRoadmapItems(activeProjectPath, itemTexts);
            toast.success(
              "Milestone Complete",
              `Marked ${result.toggled_count} items as done`
            );
          } catch (error) {
            console.error("Failed to batch mark milestone items:", error);
            toast.warning("Auto-Mark Failed", "Could not mark milestone items as done.");
          }
          useDispatchManager.getState().resetMilestonePlan();
        } else {
          // Auto-mark task as done if dispatched from a roadmap task
          if (lastDispatchContext?.itemRef?.text) {
            try {
              await api.toggleRoadmapItem(activeProjectPath, lastDispatchContext.itemRef.text);
              toast.success("Task Completed", `Marked "${lastDispatchContext.itemRef.text}" as done`);
            } catch (error) {
              console.error("Failed to auto-mark task as done:", error);
            }
          }
        }

        // After dispatch completes, check for other completed items
        reconciliationCheck(activeProjectPath, { enabled: reconciliationEnabled });
      };
      void fetchSummary();
    }
  }, [isDispatching, dispatchFailed, dispatchJobId, activeProjectPath, dispatchLogFile, reconciliationCheck, reconciliationEnabled, lastDispatchContext]);

  // Build pre-flight checks from project state
  const buildPreflightChecks = async (projectPath: string): Promise<PreFlightCheck[]> => {
    if (!isBackendConnected()) {
      return generatePreFlightChecks({
        uncommittedCount: 0,
        branch: null,
        dependenciesFresh: null,
        previousSessionStatus: null,
        editorConflict: null,
      });
    }

    try {
      const [gitStatus, timeline] = await Promise.all([
        api.getGitStatus(projectPath).catch(() => null),
        api.getTimeline(projectPath, 1).catch(() => null),
      ]);

      const uncommittedCount =
        (gitStatus?.uncommitted.length || 0) + (gitStatus?.untracked.length || 0);
      const previousSession = timeline?.entries?.[0];

      return generatePreFlightChecks({
        uncommittedCount,
        branch: gitStatus?.branch || null,
        dependenciesFresh: null,
        previousSessionStatus: derivePreviousSessionStatus(previousSession),
        editorConflict: null,
      });
    } catch {
      return generatePreFlightChecks({
        uncommittedCount: 0,
        branch: null,
        dependenciesFresh: null,
        previousSessionStatus: null,
        editorConflict: null,
      });
    }
  };

  // Show pre-flight interstitial before dispatch — always show modal
  const handleShowPreFlight = (
    prompt: string,
    mode: string,
    source: DispatchContext["source"] = "overview",
    itemRef?: DispatchContext["itemRef"]
  ) => {
    if (isDispatching) return;

    setDispatchContext({ prompt, mode, source, itemRef });
    setPreFlightChecks([]);
    setShowPreflight(true);
    void buildPreflightChecks(activeProjectPath).then((checks) => {
      setPreFlightChecks(checks);
    }).catch((err) => console.error('Failed to build preflight checks:', err));
  };

  const handleStartSession = (prompt?: string, mode?: string) => {
    void handleShowPreFlight(
      prompt || "Continue work on the current task",
      mode || "standard",
      "overview"
    );
  };

  const handleRoadmapStartSession = (item: MilestoneItem) => {
    const prompt = item.prompt || `Complete the following task: ${item.text}`;
    void handleShowPreFlight(prompt, "standard", "roadmap");
  };

  const handleRoadmapToggleDone = (item: MilestoneItem) => {
    if (!activeProjectPath) return;
    api.toggleRoadmapItem(activeProjectPath, item.text).catch((err) => {
      console.warn("Failed to toggle roadmap item:", err);
    });
  };

  const handleRoadmapEditPrompt = (_item: MilestoneItem, _newPrompt: string) => {
    // Prompt edits are kept in local component state until a backend
    // endpoint for persisting per-item prompts is available.
  };

  const handleRunParallel = (milestone: Milestone) => {
    if (useDispatchManager.getState().isDispatching) {
      toast.warning("Dispatch In Progress", "Wait for the current dispatch to finish.");
      return;
    }
    const remaining = milestone.items.filter((i) => !i.done);
    if (remaining.length < 2) {
      toast.info("Not Enough Tasks", "Parallel execution requires at least 2 remaining tasks.");
      return;
    }
    useParallelManager.getState().startPlanning(milestone, activeProjectPath);
  };

  const handleRoadmapStartMilestone = (milestone: Milestone) => {
    // Guard: don't start a new milestone plan while dispatch is running
    if (useDispatchManager.getState().isDispatching) {
      toast.warning("Dispatch In Progress", "Wait for the current dispatch to finish.");
      return;
    }
    if (useDispatchManager.getState().milestonePlanPhase !== "idle") {
      toast.warning("Milestone In Progress", "A milestone plan is already active.");
      return;
    }

    const remaining = milestone.items.filter((i) => !i.done);
    if (remaining.length === 0) return;

    const itemList = remaining
      .map((item, i) => `${i + 1}. ${item.prompt || item.text}`)
      .join("\n");

    const planPrompt = `You are planning the implementation of milestone: "${milestone.title}".

Here are the remaining tasks:
${itemList}

IMPORTANT: Do NOT make any code changes yet. Instead:
1. Analyze the codebase to understand what each task requires
2. Produce a detailed implementation plan for all tasks
3. List files that need changes for each task
4. Identify dependencies between tasks and suggest execution order
5. Flag any questions or ambiguities
6. Estimate effort per task (small/medium/large)`;

    const context = {
      milestoneId: milestone.id,
      milestoneTitle: milestone.title,
      remainingItems: remaining,
      combinedPrompt: planPrompt,
    };

    useDispatchManager.getState().startMilestonePlan(context);
    handleShowPreFlight(planPrompt, "standard", "roadmap");
  };

  const handleMilestonePlanExecute = (mode: string, userNotes?: string) => {
    executeMilestone(mode, activeProjectPath, userNotes);
  };

  const handleMilestonePlanCancel = () => {
    resetMilestonePlan();
  };

  // View session report
  const handleViewReport = async (sessionId?: string) => {
    if (!isBackendConnected()) {
      toast.warning("Backend Not Connected", "Session reports require backend connectivity.");
      return;
    }

    try {
      // Only fetch timeline (branch is already included per entry — no need for commits)
      const timeline = await api.getTimeline(activeProjectPath, 10);

      const target =
        (sessionId
          ? timeline.entries.find((entry) => entry.sessionId === sessionId)
          : timeline.entries[0]) || null;
      if (!target) {
        toast.info("No Report Data", "No session report data is available yet.");
        return;
      }

      const branch = target.branch || "unknown";
      const gates = Object.fromEntries(
        Object.entries(target.gateStatuses || {}).map(([name, status]) => [
          name,
          normalizeGateStatus(status),
        ])
      ) as Record<string, Status>;
      const tests = target.testResults
        ? {
            passed:
              target.testResults.passedCount ??
              (target.testResults.passed ? target.testResults.total || 0 : 0),
            failed: Math.max(
              0,
              (target.testResults.total || 0) - (target.testResults.passedCount || 0)
            ),
          }
        : null;

      // Fetch current uncommitted files for the changed-files section.
      // The timeline only tracks a count (filesChanged), not individual paths.
      // Git status gives us the current working tree, which is the best
      // approximation when viewing the most recent session's report.
      let files: SessionReport["files"] = [];
      try {
        const gitStatus = await api.getGitStatus(activeProjectPath);
        const allFiles = [
          ...gitStatus.uncommitted.map((f) => ({
            path: f.file,
            status: (f.status === "A" || f.status === "M" || f.status === "D" ? f.status : "M") as "A" | "M" | "D",
            lines: f.lines || "",
          })),
          ...gitStatus.untracked.map((f) => ({
            path: f.file,
            status: "A" as const,
            lines: "",
          })),
        ];
        files = allFiles;
      } catch {
        // Non-critical — show empty file list
      }

      setSelectedReport({
        sessionId: target.sessionId,
        duration: minutesToDuration(target.durationMinutes),
        cost: target.costEstimate != null ? `$${target.costEstimate.toFixed(2)}` : null,
        tokens: target.tokenUsage
          ? {
              input: target.tokenUsage.inputTokens,
              output: target.tokenUsage.outputTokens,
            }
          : null,
        provider: "claude",
        branch,
        summary: target.summary || "No summary available",
        files,
        tests,
        gates,
        roadmapMatches: target.roadmapItemsCompleted || [],
      });
      setShowReport(true);
    } catch (error) {
      console.error("Failed to load session report:", error);
      toast.error("Report Unavailable", "Unable to load session report details.");
    }
  };

  const handleNavigateToSettings = () => {
    setActiveTab(8);
  };

  const handleNavigateToGit = () => {
    setActiveTab(3);
  };

  // Execute dispatch after pre-flight approval
  const handleDispatch = async () => {
    setShowPreflight(false);
    if (!dispatchContext) return;
    const context = dispatchContext;
    setDispatchContext(null);
    await executeDispatch(context, activeProjectPath);
  };

  // Retry dispatch handler
  const handleRetryDispatch = () => {
    retryDispatch(activeProjectPath);
  };

  // Fallback dispatch handlers
  const handleRunFallback = async (provider: "codex" | "gemini") => {
    const cliPath = provider === "codex"
      ? useSettingsStore.getState().codexPath
      : useSettingsStore.getState().geminiPath;
    await runFallbackAction(provider, activeProjectPath, cliPath);
  };

  // Session report handlers
  const handleApproveReport = () => {
    // Auto-mark is handled in the dispatch completion effect (line ~223).
    // Approving a report simply closes the overlay.
    setShowReport(false);
    setSelectedReport(null);
  };

  const handleRetryWithContext = () => {
    if (!selectedReport) return;
    setShowReport(false);

    const gateSummary = Object.entries(selectedReport.gates)
      .map(([gate, status]) => `${gate}: ${status}`)
      .join(", ");

    const retryPrompt = `The previous session produced changes but had issues. Try a different approach.

Previous summary: ${selectedReport.summary}
Gate results: ${gateSummary || "No gates captured"}

Please fix the failing gates and retry.`;

    void handleShowPreFlight(retryPrompt, "standard", "overview");
  };

  const handleRevert = () => {
    setConfirmConfig({
      title: "Revert Changes",
      message:
        "This will run `git reset --hard` and undo all changes from this session. This cannot be undone.",
      confirmLabel: "Revert",
      danger: true,
      onConfirm: async () => {
        setShowReport(false);
        setSelectedReport(null);
        setShowConfirm(false);
        try {
          // Discard all uncommitted changes by restoring each file
          const gitStatus = await api.getGitStatus(activeProjectPath);
          const filesToDiscard = gitStatus.uncommitted.map((f) => f.file);
          for (const file of filesToDiscard) {
            await api.discardFile(activeProjectPath, file);
          }
          toast.success("Reverted", `Discarded changes to ${filesToDiscard.length} file(s)`);
        } catch (err) {
          toast.error("Revert Failed", err instanceof Error ? err.message : "Failed to revert changes");
        }
      },
    });
    setShowConfirm(true);
  };

  const handleFix = (gateName: string, finding: string) => {
    const fixPrompt = `Fix this ${gateName} issue: ${finding}

Only modify the minimum files needed. Run the ${gateName.toLowerCase()} gate after to verify the fix.`;

    void handleShowPreFlight(fixPrompt, "standard", "gates");
  };

  const showConfirmDialog = (config: typeof confirmConfig) => {
    setConfirmConfig(config);
    setShowConfirm(true);
  };

  // Render all tabs but only display the active one
  // This keeps tabs mounted so they don't re-fetch data on every switch
  const renderTabs = () => (
    <>
      <div className={activeTab === 0 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Overview">
          <OverviewTab
            projectPath={activeProjectPath}
            onStart={handleStartSession}
            onReport={handleViewReport}
            onNavigateToSettings={handleNavigateToSettings}
            onNavigateToGit={handleNavigateToGit}
            onShowPreFlight={handleShowPreFlight}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 1 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Roadmap">
          <RoadmapTab
            projectPath={activeProjectPath}
            isActive={activeTab === 1}
            onStartSession={handleRoadmapStartSession}
            onStartMilestone={handleRoadmapStartMilestone}
            onRunParallel={handleRunParallel}
            onToggleDone={handleRoadmapToggleDone}
            onEditPrompt={handleRoadmapEditPrompt}
            onShowConfirm={showConfirmDialog}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 2 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Timeline">
          <TimelineTab
            projectPath={activeProjectPath}
            onReport={handleViewReport}
            onShowConfirm={showConfirmDialog}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 3 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Git">
          <GitTab
            projectPath={activeProjectPath}
            isActive={activeTab === 3}
            onReport={handleViewReport}
            onShowConfirm={showConfirmDialog}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 4 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Intelligence">
          <IntelligenceTab onFix={handleFix} />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 5 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Product Map">
          <ProductMapTab onFix={handleFix} />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 6 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Quality Gates">
          <GatesTab
            projectPath={activeProjectPath}
            isActive={activeTab === 6}
            onFix={handleFix}
            onNavigateToSettings={handleNavigateToSettings}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 7 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Logs">
          <LogsTab
            projectPath={activeProjectPath}
            isActive={activeTab === 7}
            onFix={handleFix}
            onShowConfirm={showConfirmDialog}
          />
        </TabErrorBoundary>
      </div>
      <div className={activeTab === 8 ? 'block' : 'hidden'}>
        <TabErrorBoundary tabName="Settings">
          <SettingsTab
            projectPath={activeProjectPath}
            isActive={activeTab === 8}
            backendConnected={backendConnected}
            onShowConfirm={showConfirmDialog}
          />
        </TabErrorBoundary>
      </div>
    </>
  );

  if (!initialized) {
    return (
      <Dashboard>
        <div className="flex items-center justify-center h-full text-mc-text-2">
          Connecting to backend...
        </div>
      </Dashboard>
    );
  }

  return (
    <Dashboard>
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="py-5 px-6 max-w-full flex-1 overflow-y-auto">
        {!backendConnected && (
          <div className="bg-mc-amber-muted border border-mc-amber-border rounded-lg py-2 px-3 mb-4 text-xs text-mc-amber">
            Backend not connected. Live project data is unavailable.
          </div>
        )}

        {renderTabs()}
      </main>

      {/* Session Report Overlay */}
      {showReport && selectedReport && (
        <SessionReportOverlay
          report={selectedReport}
          onClose={() => {
            setShowReport(false);
            setSelectedReport(null);
          }}
          onApprove={handleApproveReport}
          onRetry={handleRetryWithContext}
          onRevert={handleRevert}
        />
      )}

      {/* Pre-Flight Interstitial */}
      {showPreflight && (
        <PreFlightInterstitial
          checks={preFlightChecks}
          hooks={preSessionHooks}
          prompt={dispatchContext?.prompt}
          mode={dispatchContext?.mode}
          onClose={() => {
            setShowPreflight(false);
            setDispatchContext(null);
            // Reset milestone plan if user cancels from PreFlight
            if (milestonePlanPhase === "planning") {
              resetMilestonePlan();
            }
          }}
          onDispatch={handleDispatch}
        />
      )}

      {/* Milestone Plan Review — visible during planning (only once dispatch is running) and reviewing */}
      {((milestonePlanPhase === "planning" && isDispatching) || milestonePlanPhase === "reviewing") && milestonePlanContext && (
        <MilestonePlanReview
          milestoneTitle={milestonePlanContext.milestoneTitle}
          remainingItems={milestonePlanContext.remainingItems}
          planOutput={milestonePlanOutput || ""}
          isPlanning={milestonePlanPhase === "planning"}
          onExecute={handleMilestonePlanExecute}
          onCancel={handleMilestonePlanCancel}
        />
      )}

      {/* Confirm Dialog */}
      {showConfirm && confirmConfig && (
        <ConfirmDialog
          title={confirmConfig.title}
          message={confirmConfig.message}
          confirmLabel={confirmConfig.confirmLabel}
          danger={confirmConfig.danger}
          onConfirm={() => {
            confirmConfig.onConfirm();
            setShowConfirm(false);
            setConfirmConfig(null);
          }}
          onCancel={() => {
            setShowConfirm(false);
            setConfirmConfig(null);
          }}
        />
      )}

      {/* Fallback Modal */}
      {showFallbackModal && fallbackPrompt && (
        <FallbackModal
          prompt={fallbackPrompt}
          preferredProvider={preferredFallback}
          isRunning={isFallbackRunning}
          runningProvider={fallbackProvider}
          output={fallbackOutput}
          error={fallbackError}
          errorCode={fallbackErrorCode}
          statusText={fallbackStatusText}
          phase={fallbackPhase}
          onRun={handleRunFallback}
          onClose={closeFallback}
        />
      )}

      {/* Dispatch Overlay and Minimized Indicator — suppressed during milestone plan phases */}
      {milestonePlanPhase !== "planning" && milestonePlanPhase !== "reviewing" && (
        <>
          <DispatchOverlay onRetry={handleRetryDispatch} />
          <DispatchMinimized />
        </>
      )}

      {/* Dispatch Summary */}
      {showDispatchSummary && dispatchSummary && (
        <DispatchSummary
          success={dispatchSummary.success}
          filesChanged={dispatchSummary.files_changed}
          totalAdded={dispatchSummary.total_added}
          totalRemoved={dispatchSummary.total_removed}
          summaryMessage={dispatchSummary.summary_message}
          hasErrors={dispatchSummary.has_errors}
          outputTail={dispatchOutputTail}
          onReviewChanges={() => {
            setShowDispatchSummary(false);
            setDispatchSummary(null);
            useDispatchManager.getState().reset();
            setActiveTab(3); // Navigate to Git tab
          }}
          onMarkComplete={() => {
            // Task is already auto-marked as done on dispatch completion
            setShowDispatchSummary(false);
            setDispatchSummary(null);
            // Clean up any stale milestone state (edge case)
            useDispatchManager.getState().resetMilestonePlan();
            useDispatchManager.getState().reset();
          }}
          onCommit={() => {
            setShowDispatchSummary(false);
            setDispatchSummary(null);
            useDispatchManager.getState().reset();
            setActiveTab(3); // Navigate to Git tab
            toast.info("Commit", "Review changes in Git tab and commit when ready");
          }}
          onClose={() => {
            setShowDispatchSummary(false);
            setDispatchSummary(null);
            useDispatchManager.getState().reset();
          }}
        />
      )}

      {/* Parallel Execution Overlay */}
      <ParallelExecutionOverlay projectPath={activeProjectPath} />

      {/* Reconciliation Components */}
      <ReconciliationFooter projectPath={activeProjectPath} />
      <ReconciliationModal projectPath={activeProjectPath} />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </Dashboard>
  );
}
