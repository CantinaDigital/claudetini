import { create } from "zustand";
import { api } from "../api/backend";
import { useSettingsStore } from "../stores/settingsStore";
import type {
  Milestone,
  MilestoneItem,
  ParallelPhase,
  ExecutionPlan,
  AgentSlotStatus,
  MergeResultStatus,
  VerificationResult,
} from "../types";

interface ParallelManagerState {
  // Lifecycle
  phase: ParallelPhase;
  milestoneTitle: string | null;
  tasks: MilestoneItem[];
  error: string | null;

  // Planning
  planJobId: string | null;
  planOutputFile: string | null;
  planOutputTail: string | null;
  plan: ExecutionPlan | null;
  userFeedback: string;

  // Git dirty tree
  isDirty: boolean;
  dirtyFiles: string[];
  commitMessage: string;
  isGeneratingMessage: boolean;
  isCommitting: boolean;
  commitError: string | null;

  // Execution
  batchId: string | null;
  agents: AgentSlotStatus[];
  mergeResults: MergeResultStatus[];
  currentPhaseId: number;
  currentPhaseName: string;

  // Verification
  verification: VerificationResult | null;
  verificationOutputTail: string | null;

  // Finalize
  finalizeMessage: string | null;

  totalCost: number;
  showOverlay: boolean;

  // Actions
  startPlanning: (milestone: Milestone, projectPath: string) => Promise<void>;
  approvePlan: (projectPath: string) => Promise<void>;
  replan: (projectPath: string) => Promise<void>;
  cancel: () => Promise<void>;
  closeOverlay: (projectPath?: string) => void;
  reset: () => void;
  cleanup: () => void;

  // Git commit actions
  setCommitMessage: (msg: string) => void;
  generateCommitMessage: (projectPath: string) => Promise<void>;
  commitAndProceed: (projectPath: string) => Promise<void>;

  // Feedback
  setUserFeedback: (feedback: string) => void;
}

let _pollInterval: ReturnType<typeof setInterval> | null = null;

// ── localStorage persistence for HMR / reload survival ──
const STORAGE_KEY = "cantina:parallel-execution";

interface PersistedState {
  batchId: string;
  phase: ParallelPhase;
  milestoneTitle: string | null;
}

function _persistState(batchId: string, phase: ParallelPhase, milestoneTitle: string | null): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ batchId, phase, milestoneTitle }));
  } catch { /* quota or private mode — ignore */ }
}

function _clearPersistedState(): void {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
}

function _loadPersistedState(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedState;
    if (!parsed.batchId) return null;
    return parsed;
  } catch { return null; }
}

const INITIAL_STATE = {
  phase: "idle" as ParallelPhase,
  milestoneTitle: null as string | null,
  tasks: [] as MilestoneItem[],
  error: null as string | null,
  planJobId: null as string | null,
  planOutputFile: null as string | null,
  planOutputTail: null as string | null,
  plan: null as ExecutionPlan | null,
  userFeedback: "",
  isDirty: false,
  dirtyFiles: [] as string[],
  commitMessage: "",
  isGeneratingMessage: false,
  isCommitting: false,
  commitError: null as string | null,
  batchId: null as string | null,
  agents: [] as AgentSlotStatus[],
  mergeResults: [] as MergeResultStatus[],
  currentPhaseId: 0,
  currentPhaseName: "",
  verification: null as VerificationResult | null,
  verificationOutputTail: null as string | null,
  finalizeMessage: null as string | null,
  totalCost: 0,
  showOverlay: false,
};

export const useParallelManager = create<ParallelManagerState>((set, get) => ({
  ...INITIAL_STATE,

  startPlanning: async (milestone, projectPath) => {
    const remaining = milestone.items.filter((i) => !i.done);
    if (remaining.length < 2) return;

    set({
      ...INITIAL_STATE,
      phase: "git_check",
      milestoneTitle: milestone.title,
      tasks: remaining,
      showOverlay: true,
    });

    // Step 1: Check git FIRST — gate everything on a clean tree
    try {
      const gitResult = await api.parallelGitCheck(projectPath);
      if (!gitResult.clean) {
        // Dirty tree — show commit UI, don't start planning
        set({
          isDirty: true,
          dirtyFiles: gitResult.dirty_files,
        });
        return;
      }
    } catch {
      // Can't check git — proceed anyway (orchestrator will catch if truly dirty)
    }

    // Step 2: Tree is clean — proceed to planning
    _startPlanningAgent(set, get, remaining, milestone.title, projectPath);
  },

  approvePlan: async (projectPath) => {
    const { tasks, plan } = get();
    if (!plan) return;

    const maxParallel = useSettingsStore.getState().maxParallelAgents;

    set({ phase: "executing", error: null });

    try {
      const taskPayload = tasks.map((item) => ({
        text: item.text,
        prompt: item.prompt || item.text,
      }));

      const result = await api.parallelExecute(
        projectPath,
        taskPayload,
        plan,
        maxParallel
      );
      set({ batchId: result.batch_id });
      _persistState(result.batch_id, "executing", get().milestoneTitle);

      // Start polling execution status
      _startExecutionPolling(set, get, result.batch_id);
    } catch (err) {
      set({
        phase: "failed",
        error: err instanceof Error ? err.message : "Failed to start execution",
      });
    }
  },

  replan: async (projectPath) => {
    const { tasks, plan, userFeedback, milestoneTitle } = get();
    if (!plan || !userFeedback.trim()) return;

    const lightModel = useSettingsStore.getState().lightModel;

    set({ phase: "replanning", error: null, planOutputTail: null });

    try {
      const taskPayload = tasks.map((item) => ({
        text: item.text,
        prompt: item.prompt || item.text,
      }));

      const result = await api.parallelReplan(
        projectPath,
        taskPayload,
        plan,
        userFeedback,
        milestoneTitle || "",
        lightModel
      );

      set({
        planJobId: result.plan_job_id,
        planOutputFile: result.output_file,
        userFeedback: "",
      });

      // Start polling new plan
      _startPlanPolling(set, get, result.plan_job_id);
    } catch (err) {
      set({
        phase: "plan_review",
        error: err instanceof Error ? err.message : "Re-planning failed",
      });
    }
  },

  cancel: async () => {
    const { planJobId, batchId } = get();
    const idToCancel = batchId || planJobId;
    if (idToCancel) {
      try {
        await api.parallelCancel(idToCancel);
      } catch {
        // Best effort
      }
    }
    _stopPolling();
    set({
      phase: "cancelled",
      error: "Cancelled by user",
    });
  },

  closeOverlay: (projectPath?: string) => {
    _stopPolling();
    _clearPersistedState();
    // Release HMR lock so Vite resumes normal operation
    if (projectPath) {
      api.parallelReleaseHmrLock(projectPath).catch(() => {});
    }
    set({ ...INITIAL_STATE });
  },

  reset: () => {
    _stopPolling();
    _clearPersistedState();
    set({ ...INITIAL_STATE });
  },

  cleanup: () => {
    _stopPolling();
  },

  // Git actions

  setCommitMessage: (msg) => set({ commitMessage: msg }),

  generateCommitMessage: async (projectPath) => {
    set({ isGeneratingMessage: true });
    try {
      const lightModel = useSettingsStore.getState().lightModel;
      const result = await api.generateCommitMessageAI(projectPath, lightModel);
      set({ commitMessage: result.message, isGeneratingMessage: false });
    } catch {
      set({ isGeneratingMessage: false });
    }
  },

  commitAndProceed: async (projectPath) => {
    const { commitMessage, tasks, milestoneTitle } = get();
    if (!commitMessage.trim()) return;

    set({ isCommitting: true, commitError: null });
    try {
      await api.stageAll(projectPath);
      await api.commitStaged(projectPath, commitMessage);

      // Re-check git status after commit
      const gitResult = await api.parallelGitCheck(projectPath);
      if (!gitResult.clean) {
        // Still dirty after commit — show remaining files
        set({
          isCommitting: false,
          commitMessage: "",
          dirtyFiles: gitResult.dirty_files,
          commitError: `${gitResult.dirty_files.length} file(s) still have changes after commit`,
        });
        return;
      }

      // Clean — auto-proceed to planning
      set({
        isDirty: false,
        dirtyFiles: [],
        commitMessage: "",
        isCommitting: false,
        commitError: null,
      });
      _startPlanningAgent(set, get, tasks, milestoneTitle || "", projectPath);
    } catch (err) {
      set({
        isCommitting: false,
        commitError: err instanceof Error ? err.message : "Commit failed",
      });
    }
  },

  setUserFeedback: (feedback) => set({ userFeedback: feedback }),
}));

/** Start the planning agent and begin polling. */
function _startPlanningAgent(
  set: (partial: Partial<ParallelManagerState>) => void,
  get: () => ParallelManagerState,
  tasks: MilestoneItem[],
  milestoneTitle: string,
  projectPath: string
): void {
  const lightModel = useSettingsStore.getState().lightModel;

  set({ phase: "planning", error: null });

  const taskPayload = tasks.map((item) => ({
    text: item.text,
    prompt: item.prompt || item.text,
  }));

  api
    .parallelPlan(projectPath, taskPayload, milestoneTitle, lightModel)
    .then((result) => {
      set({ planJobId: result.plan_job_id, planOutputFile: result.output_file });
      _startPlanPolling(set, get, result.plan_job_id);
    })
    .catch((err) => {
      set({
        phase: "failed",
        error: err instanceof Error ? err.message : "Planning failed",
      });
    });
}

function _startPlanPolling(
  set: (partial: Partial<ParallelManagerState>) => void,
  _get: () => ParallelManagerState,
  planJobId: string
): void {
  _stopPolling();

  _pollInterval = setInterval(async () => {
    try {
      const status = await api.parallelPlanStatus(planJobId);

      set({ planOutputTail: status.output_tail });

      if (status.status === "complete" && status.plan) {
        _stopPolling();
        set({
          phase: "plan_review",
          plan: status.plan,
          error: null,
        });
      } else if (status.status === "failed") {
        _stopPolling();
        set({
          phase: "failed",
          error: status.error || "Planning failed",
        });
      }
      // "running" → keep polling
    } catch {
      // Polling failure — keep trying
    }
  }, 2000);
}

function _startExecutionPolling(
  set: (partial: Partial<ParallelManagerState>) => void,
  _get: () => ParallelManagerState,
  batchId: string
): void {
  _stopPolling();

  _pollInterval = setInterval(async () => {
    try {
      const status = await api.parallelExecuteStatus(batchId);

      set({
        phase: status.phase,
        agents: status.agents,
        mergeResults: status.merge_results,
        currentPhaseId: status.current_phase_id,
        currentPhaseName: status.current_phase_name,
        totalCost: status.total_cost,
        verification: status.verification,
        verificationOutputTail: status.verification_output_tail,
        finalizeMessage: status.finalize_message,
        error: status.error,
      });

      // Stop polling if done
      const terminal: ParallelPhase[] = ["complete", "failed", "cancelled"];
      if (terminal.includes(status.phase)) {
        _stopPolling();
        _clearPersistedState();
      }
    } catch {
      // Polling failure — keep trying
    }
  }, 2000);
}

function _stopPolling(): void {
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

// ── Auto-resume after HMR / page reload ──
// Check localStorage for an in-progress execution and resume polling.
function _tryResumeExecution(): void {
  const persisted = _loadPersistedState();
  if (!persisted) return;

  const terminal: ParallelPhase[] = ["complete", "failed", "cancelled", "idle"];
  if (terminal.includes(persisted.phase)) {
    _clearPersistedState();
    return;
  }

  // Restore minimal state and start polling — the first poll response
  // will fill in agents, mergeResults, verification, etc.
  const { setState, getState } = useParallelManager;
  setState({
    batchId: persisted.batchId,
    phase: persisted.phase,
    milestoneTitle: persisted.milestoneTitle,
    showOverlay: true,
  });

  _startExecutionPolling(
    (partial) => setState(partial),
    () => getState(),
    persisted.batchId,
  );
}

// Run resume check on module load (fires on initial load AND Vite HMR re-execution)
_tryResumeExecution();
