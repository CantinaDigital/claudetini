import { create } from "zustand";
import { api, isBackendConnected, API_BASE_URL } from "../api/backend";
import { toast } from "../components/ui/Toast";
import type {
  StreamEvent,
  StreamStartResult,
  StreamCompletionStatus,
  QueuedDispatch,
  MilestonePlanPhase,
  MilestonePlanContext,
} from "../types";

// -------------------------------------------------------
// Types
// -------------------------------------------------------

export interface DispatchContext {
  prompt: string;
  mode: string;
  source: "overview" | "roadmap" | "ask" | "task" | "queue" | "fix" | "gates" | "logs" | "timeline";
  itemRef?: { text: string; prompt?: string };
}

type DispatchPhase =
  | "idle"
  | "starting"
  | "streaming"
  | "polling"
  | "completing"
  | "failed"
  | "token_limit"
  | "cancelled";

type FallbackPhase = "idle" | "queued" | "running" | "complete" | "failed";

// -------------------------------------------------------
// Module-level resources (not in reactive state)
// -------------------------------------------------------

let timerInterval: ReturnType<typeof setInterval> | null = null;
let eventSource: EventSource | null = null;
let projectPathRef: string | null = null;
let sseJobId: string | null = null; // Tracks job_id received from SSE stream start
let lastTailLineCount = 0; // Tracks last line count for output tailing during polling

function clearTimer(): void {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function closeEventSource(): void {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

// -------------------------------------------------------
// Store
// -------------------------------------------------------

interface DispatchManagerState {
  // Phase state machine
  phase: DispatchPhase;
  jobId: string | null;
  startedAt: number | null;
  elapsedSeconds: number;
  progressPct: number;
  statusText: string;
  context: DispatchContext | null;
  lastContext: DispatchContext | null;
  promptPreview: string;
  streamOutputLines: string[];
  streamSequence: number;
  outputTail: string | null;
  logFile: string | null;
  errorDetail: string | null;
  showOverlay: boolean;

  // Fallback
  fallbackPhase: FallbackPhase;
  fallbackPrompt: string | null;
  fallbackOutput: string | null;
  fallbackError: string | null;
  fallbackErrorCode: string | null;
  fallbackJobId: string | null;
  fallbackStatusText: string;
  fallbackProvider: "codex" | "gemini" | null;

  // Queue
  queue: QueuedDispatch[];

  // Milestone Plan Mode
  milestonePlanPhase: MilestonePlanPhase;
  milestonePlanContext: MilestonePlanContext | null;
  milestonePlanOutput: string | null;

  // Derived (computed from phase)
  isDispatching: boolean;
  dispatchFailed: boolean;
  isStreaming: boolean;
  showFallbackModal: boolean;
  isFallbackRunning: boolean;

  // Actions
  setContext: (context: DispatchContext | null) => void;
  removeFromQueue: (id: string) => void;
  dispatchNext: (projectPath: string) => void;
  execute: (context: DispatchContext, projectPath: string) => Promise<void>;
  cancel: () => Promise<void>;
  retry: (projectPath: string) => void;
  runFallback: (
    provider: "codex" | "gemini",
    projectPath: string,
    cliPath?: string
  ) => Promise<void>;
  closeFallback: () => void;
  closeOverlay: () => void;
  reset: () => void;
  cleanup: () => void;

  // Milestone Plan Actions
  startMilestonePlan: (context: MilestonePlanContext) => void;
  completePlanPhase: (planOutput: string) => void;
  executeMilestone: (mode: string, projectPath: string, userNotes?: string) => void;
  resetMilestonePlan: () => void;
}

function getDispatchFlags(mode: string): string {
  switch (mode) {
    case "with-review":
      return "--agents";
    case "full-pipeline":
      return "--agents --full-pipeline";
    case "blitz":
      return "--blitz";
    default:
      return "";
  }
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function buildFallbackPrompt(
  prompt: string,
  provider: "codex" | "gemini"
): string {
  const label = provider === "codex" ? "Codex" : "Gemini";
  return `You are running as an automated ${label} fallback dispatch for Claudetini.

Critical requirements:
- Do not ask clarifying questions.
- Do not wait for confirmation.
- Do not open interactive prompts.
- Keep unrelated dirty files untouched.
- Modify only files needed to fix the failing gates described below.
- Before final answer, run the relevant gates and report pass/fail for each.

Task:
${prompt}`;
}

export const useDispatchManager = create<DispatchManagerState>((set, get) => ({
  // Initial state
  phase: "idle",
  jobId: null,
  startedAt: null,
  elapsedSeconds: 0,
  progressPct: 0,
  statusText: "",
  context: null,
  lastContext: null,
  promptPreview: "",
  streamOutputLines: [],
  streamSequence: 0,
  outputTail: null,
  logFile: null,
  errorDetail: null,
  showOverlay: false,

  // Fallback initial
  fallbackPhase: "idle",
  fallbackPrompt: null,
  fallbackOutput: null,
  fallbackError: null,
  fallbackErrorCode: null,
  fallbackJobId: null,
  fallbackStatusText: "",
  fallbackProvider: null,

  // Queue
  queue: [],

  // Milestone Plan Mode
  milestonePlanPhase: "idle",
  milestonePlanContext: null,
  milestonePlanOutput: null,

  // Derived
  isDispatching: false,
  dispatchFailed: false,
  isStreaming: false,
  showFallbackModal: false,
  isFallbackRunning: false,

  // -------------------------------------------------------
  // Actions
  // -------------------------------------------------------

  setContext: (context) => set({ context }),

  removeFromQueue: (id) => {
    set((state) => ({ queue: state.queue.filter((q) => q.id !== id) }));
  },

  dispatchNext: (projectPath) => {
    const { isDispatching, queue, execute } = get();
    if (isDispatching || queue.length === 0) return;
    const [next, ...rest] = queue;
    set({ queue: rest });
    const ctx: DispatchContext = {
      prompt: next.prompt,
      mode: next.mode,
      source: next.source as DispatchContext["source"],
      itemRef: next.itemRef,
    };
    void execute(ctx, projectPath);
  },

  execute: async (context, projectPath) => {
    const { prompt, mode } = context;
    const flags = getDispatchFlags(mode);

    if (!isBackendConnected()) {
      toast.warning("Backend Not Connected", "Cannot dispatch without backend.");
      return;
    }

    // Guard: prevent double-dispatch
    if (get().isDispatching) {
      console.warn("Dispatch already in progress, ignoring duplicate execute()");
      return;
    }

    // Clean up any lingering resources from previous dispatch
    clearTimer();
    closeEventSource();

    projectPathRef = projectPath;

    // Start dispatch state
    set({
      phase: "starting",
      isDispatching: true,
      dispatchFailed: false,
      errorDetail: null,
      outputTail: null,
      logFile: null,
      startedAt: Date.now(),
      elapsedSeconds: 0,
      progressPct: 4,
      promptPreview: prompt.replace(/\s+/g, " ").trim(),
      statusText: "Queueing dispatch job...",
      jobId: null,
      showOverlay: true,
      lastContext: context,
      context: null,
      isStreaming: false,
      streamSequence: 0,
      streamOutputLines: [],
    });

    // Start elapsed timer
    startTimer();

    toast.info("Dispatching...", "Running task via Claude Code");

    try {
      // Try SSE streaming first
      const streamOk = await attemptStreaming(prompt, projectPath);
      if (streamOk) return; // SSE handled completion
    } catch {
      // SSE failed, fall through to polling
      console.warn("SSE streaming failed, falling back to polling");
    }

    // Ensure EventSource is fully closed before starting polling fallback
    closeEventSource();

    // Polling fallback — reuse the SSE job_id if available to avoid duplicate jobs
    try {
      set({ phase: "polling", isStreaming: false });

      let jobIdForPolling: string;
      if (sseJobId) {
        // SSE started a job before failing; poll that instead of creating a new one
        jobIdForPolling = sseJobId;
        set({
          jobId: sseJobId,
          progressPct: Math.max(get().progressPct, 8),
          statusText: "Reconnecting via polling...",
        });
      } else {
        const start = await api.dispatchStart(projectPath, { prompt, mode, flags });
        jobIdForPolling = start.job_id;
        set({
          jobId: start.job_id,
          progressPct: Math.max(get().progressPct, 8),
          statusText: start.message || "Dispatch queued.",
        });
      }

      const status = await pollDispatchJob(jobIdForPolling);
      set({
        statusText: status.message || "",
        errorDetail: status.error_detail || null,
        outputTail: status.output_tail || null,
        logFile: status.log_file || null,
      });

      const result = status.result;
      if (!result) {
        throw new Error(
          status.error_detail || "Dispatch finished without a result payload."
        );
      }

      if (result.success) {
        // Milestone plan-phase interception: transition to review instead of full completion
        const currentPlanPhase = get().milestonePlanPhase;
        if (currentPlanPhase === "planning") {
          let planOutput = get().streamOutputLines.join("\n");

          // Try to get full output (not just tail) for plan review
          if (!planOutput && status.log_file) {
            try {
              const sessionId = status.log_file.split("/").pop()?.replace(".log", "") || "";
              const fullOutput = await api.readDispatchOutput(sessionId);
              if (fullOutput.exists && fullOutput.lines.length > 0) {
                planOutput = fullOutput.lines.join("\n");
              }
            } catch { /* fall through to output_tail */ }
          }

          if (!planOutput) {
            planOutput = status.output_tail || "";
          }

          get().completePlanPhase(planOutput);
          completeDispatch();
          toast.success("Plan Generated", "Review the plan and choose how to execute.");
          return;
        }

        completeDispatch();
        toast.success("Dispatch Successful", "Claude Code completed the task.");
        return;
      }

      // Check for token/credit limit issues
      const errorText = (
        result.error ||
        status.error_detail ||
        ""
      ).toLowerCase();
      const isCreditOrTokenLimit =
        result.token_limit_reached ||
        errorText.includes("you've exceeded your usage limit") ||
        errorText.includes("your claude.ai usage limit") ||
        errorText.includes("please wait until your limit resets");

      if (isCreditOrTokenLimit) {
        triggerFallback(
          prompt,
          result.output || status.output_tail || null,
          result.error || status.error_detail || null
        );
        toast.warning(
          "Claude Code limit reached",
          "Select Codex or Gemini to continue."
        );
        return;
      }

      failDispatch(
        result.error || "Claude Code failed. See details in overlay.",
        status.output_tail,
        status.log_file
      );
      toast.error(
        "Dispatch Failed",
        result.error || "Claude Code failed. See details in overlay."
      );
    } catch (e) {
      console.error("Dispatch failed:", e);
      const message =
        e instanceof Error
          ? e.message
          : "Failed to launch Claude Code session";
      failDispatch(message);
      toast.error("Dispatch Failed", message);
    }
  },

  cancel: async () => {
    const { jobId, isStreaming: streaming } = get();

    // Cancel SSE if active
    closeEventSource();

    if (!jobId || !isBackendConnected()) {
      cancelDispatch();
      toast.info("Dispatch Cancelled", "Job cancelled locally.");
      return;
    }

    try {
      const result = streaming
        ? await api.cancelStream(jobId)
        : await api.cancelDispatch(jobId);

      if (result.success) {
        toast.info("Dispatch Cancelled", "Job cancelled successfully.");
      } else {
        toast.warning("Cancel Failed", result.message);
      }
    } catch {
      toast.info("Dispatch Cancelled", "Job cancelled locally.");
    } finally {
      // Guarantee cleanup regardless of cancel API result
      cancelDispatch();
    }
  },

  retry: (projectPath) => {
    const { lastContext, execute } = get();
    if (!lastContext) return;
    set({ errorDetail: null, outputTail: null, logFile: null });
    void execute(lastContext, projectPath);
  },

  runFallback: async (provider, projectPath, cliPath) => {
    const { fallbackPrompt } = get();
    if (!fallbackPrompt) return;

    if (!isBackendConnected()) {
      toast.warning(
        "Backend Not Connected",
        "Cannot run fallback dispatch without backend."
      );
      return;
    }

    const providerLabel = provider === "codex" ? "Codex" : "Gemini";
    const dispatchPrompt = buildFallbackPrompt(fallbackPrompt, provider);

    set({
      fallbackPhase: "queued",
      isFallbackRunning: true,
      fallbackProvider: provider,
      fallbackError: null,
      fallbackErrorCode: null,
      fallbackStatusText: "Queueing fallback dispatch...",
      fallbackJobId: null,
      fallbackOutput: null,
    });

    toast.info(`Running via ${provider}`, `Using ${providerLabel} CLI`);

    try {
      const start = await api.dispatchFallbackStart({
        provider,
        prompt: dispatchPrompt,
        projectPath,
        cliPath,
      });

      set({
        fallbackJobId: start.job_id,
        fallbackStatusText: start.message || "Fallback job started.",
        fallbackPhase: "running",
      });

      // Poll fallback
      const maxPolls = 45 * 60;
      let finalStatus = null;
      for (let i = 0; i < maxPolls; i++) {
        const status = await api.getDispatchFallbackStatus(start.job_id);
        finalStatus = status;
        set({
          fallbackStatusText:
            status.message || `${providerLabel} is processing your task.`,
          fallbackPhase: (status.phase as FallbackPhase) || "running",
        });
        if (status.output_tail) {
          set({ fallbackOutput: status.output_tail });
        }
        if (status.done) break;
        await wait(1000);
      }

      if (!finalStatus || !finalStatus.done || !finalStatus.result) {
        throw new Error(
          "Fallback dispatch status polling timed out before completion."
        );
      }

      const result = finalStatus.result;
      set({
        fallbackOutput:
          result.output || finalStatus.output_tail || null,
      });

      if (result.success) {
        set({
          fallbackError: null,
          fallbackErrorCode: null,
          fallbackStatusText: "Fallback completed successfully.",
          fallbackPhase: "complete",
        });
        toast.success(
          "Fallback Dispatch Successful",
          `Task completed via ${providerLabel}.`
        );
      } else {
        const message =
          result.error ||
          finalStatus.error_detail ||
          "Fallback dispatch failed before completion";
        set({
          fallbackError: message,
          fallbackErrorCode: result.error_code ?? null,
          fallbackStatusText: message,
          fallbackPhase: "failed",
        });
        toast.error("Fallback Dispatch Failed", message);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Fallback dispatch failed";
      set({
        fallbackError: message,
        fallbackErrorCode: "execution_failed",
        fallbackStatusText: message,
        fallbackPhase: "failed",
      });
      toast.error("Fallback Dispatch Failed", message);
    } finally {
      set({ isFallbackRunning: false, fallbackProvider: null, fallbackJobId: null });
    }
  },

  closeFallback: () => {
    const { isFallbackRunning } = get();
    if (isFallbackRunning) return;
    set({
      showFallbackModal: false,
      fallbackPrompt: null,
      fallbackOutput: null,
      fallbackError: null,
      fallbackErrorCode: null,
      fallbackJobId: null,
      fallbackStatusText: "",
      fallbackPhase: "idle",
    });
  },

  closeOverlay: () => {
    const { isDispatching } = get();
    if (isDispatching) {
      set({ showOverlay: false });
      return;
    }
    set({
      dispatchFailed: false,
      errorDetail: null,
      outputTail: null,
      logFile: null,
      jobId: null,
      statusText: "",
      promptPreview: "",
      progressPct: 0,
      showOverlay: false,
      isStreaming: false,
      streamSequence: 0,
      streamOutputLines: [],
    });
  },

  reset: () => {
    clearTimer();
    closeEventSource();
    set({
      phase: "idle",
      isDispatching: false,
      startedAt: null,
      elapsedSeconds: 0,
      progressPct: 0,
      jobId: null,
      logFile: null,
      outputTail: null,
      promptPreview: "",
      statusText: "",
    });
  },

  cleanup: () => {
    clearTimer();
    closeEventSource();
  },

  // -------------------------------------------------------
  // Milestone Plan Actions
  // -------------------------------------------------------

  startMilestonePlan: (context) => {
    set({
      milestonePlanPhase: "planning",
      milestonePlanContext: context,
      milestonePlanOutput: null,
    });
  },

  completePlanPhase: (planOutput) => {
    set({
      milestonePlanPhase: "reviewing",
      milestonePlanOutput: planOutput,
    });
  },

  executeMilestone: (mode, projectPath, userNotes) => {
    const { milestonePlanContext, milestonePlanOutput, execute } = get();
    if (!milestonePlanContext) return;

    const items = milestonePlanContext.remainingItems;
    const itemList = items
      .map((item, i) => `${i + 1}. ${item.prompt || item.text}`)
      .join("\n");

    let execPrompt = `You are implementing milestone: "${milestonePlanContext.milestoneTitle}".

Here are the tasks to implement:
${itemList}

Here is the implementation plan from the planning phase:
---
${milestonePlanOutput || "(no plan output)"}
---
`;

    if (userNotes?.trim()) {
      execPrompt += `\nAdditional notes from the developer:\n${userNotes.trim()}\n`;
    }

    execPrompt += `\nIMPORTANT: Implement ALL tasks listed above. Follow the plan. Make all necessary code changes.`;

    set({ milestonePlanPhase: "executing" });

    const ctx: DispatchContext = {
      prompt: execPrompt,
      mode,
      source: "roadmap",
    };

    void execute(ctx, projectPath);
  },

  resetMilestonePlan: () => {
    set({
      milestonePlanPhase: "idle",
      milestonePlanContext: null,
      milestonePlanOutput: null,
    });
  },
}));

// -------------------------------------------------------
// Internal helpers (module-scoped)
// -------------------------------------------------------

function startTimer(): void {
  clearTimer();
  timerInterval = window.setInterval(() => {
    const { startedAt } = useDispatchManager.getState();
    if (startedAt == null) return;
    const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    useDispatchManager.setState({
      elapsedSeconds: elapsed,
      progressPct: Math.min(94, Math.max(useDispatchManager.getState().progressPct, 12 + elapsed * 2)),
    });
  }, 1000);
}

function completeDispatch(): void {
  clearTimer();
  closeEventSource();
  useDispatchManager.setState({
    phase: "idle",
    progressPct: 100,
    isDispatching: false,
    startedAt: null,
    elapsedSeconds: 0,
    showOverlay: false,
    promptPreview: "",
    statusText: "",
    isStreaming: false,
    streamSequence: 0,
    streamOutputLines: [],
  });
}

function failDispatch(
  error: string,
  output?: string | null,
  logFile?: string | null
): void {
  clearTimer();
  closeEventSource();
  useDispatchManager.setState({
    phase: "failed",
    dispatchFailed: true,
    progressPct: 100,
    errorDetail: error,
    outputTail: output ?? null,
    logFile: logFile ?? null,
    statusText: "Dispatch failed before completion.",
    isDispatching: false,
    startedAt: null,
    elapsedSeconds: 0,
    showOverlay: true,
  });
}

function cancelDispatch(): void {
  clearTimer();
  closeEventSource();
  useDispatchManager.setState({
    phase: "cancelled",
    isDispatching: false,
    dispatchFailed: false,
    startedAt: null,
    elapsedSeconds: 0,
    progressPct: 0,
    jobId: null,
    promptPreview: "",
    statusText: "",
    errorDetail: null,
    outputTail: null,
    logFile: null,
    showOverlay: false,
    isStreaming: false,
    streamSequence: 0,
    streamOutputLines: [],
  });
}

function triggerFallback(
  prompt: string,
  output: string | null,
  error: string | null
): void {
  clearTimer();
  closeEventSource();
  useDispatchManager.setState({
    phase: "token_limit",
    showFallbackModal: true,
    fallbackPrompt: prompt,
    fallbackOutput: output,
    fallbackError: error,
    fallbackErrorCode: null,
    fallbackJobId: null,
    fallbackStatusText: "",
    fallbackPhase: "idle",
    isDispatching: false,
    startedAt: null,
    elapsedSeconds: 0,
    jobId: null,
    promptPreview: "",
    statusText: "",
    progressPct: 0,
    showOverlay: false,
  });
}

async function pollDispatchJob(
  jobId: string
): Promise<ReturnType<typeof api.getDispatchStatus>> {
  lastTailLineCount = 0;
  const maxPolls = 45 * 60;
  for (let i = 0; i < maxPolls; i++) {
    try {
      const status = await api.getDispatchStatus(jobId);
      useDispatchManager.setState({
        statusText: status.message || "Claude Code is processing your task.",
      });

      if (status.output_tail) {
        useDispatchManager.setState({
          outputTail: status.output_tail,
          logFile: status.log_file ?? useDispatchManager.getState().logFile,
        });
      } else if (i > 5) {
        useDispatchManager.setState({
          outputTail: null,
          logFile: status.log_file ?? useDispatchManager.getState().logFile,
        });
      }

      // Tail the output file for live CLI output (replaces useOutputTail hook)
      const currentLogFile = status.log_file ?? useDispatchManager.getState().logFile;
      if (currentLogFile && status.status === "running") {
        try {
          const sessionId = currentLogFile.split("/").pop()?.replace(".log", "") || currentLogFile;
          const tailResult = await api.readDispatchOutput(sessionId);
          if (tailResult.exists && tailResult.lines.length > lastTailLineCount) {
            const newTail = tailResult.lines.slice(-24).join("\n");
            lastTailLineCount = tailResult.lines.length;
            useDispatchManager.setState({ outputTail: newTail });
          }
        } catch {
          // Non-critical: output tailing failure doesn't affect dispatch
        }
      }

      if (status.status === "queued") {
        useDispatchManager.setState({
          progressPct: Math.max(useDispatchManager.getState().progressPct, 8),
        });
      }
      if (status.status === "running") {
        useDispatchManager.setState({
          progressPct: Math.max(useDispatchManager.getState().progressPct, 30),
        });
      }
      if (status.done) return status;
    } catch (error) {
      console.error(`Poll #${i + 1} failed:`, error);
      if (i > 5) {
        useDispatchManager.setState({
          statusText: `Polling error (attempt ${i + 1}). Retrying...`,
        });
      }
    }
    await wait(1000);
  }
  throw new Error("Dispatch status polling timed out after 45 minutes.");
}

async function attemptStreaming(
  prompt: string,
  projectPath: string
): Promise<boolean> {
  sseJobId = null;
  useDispatchManager.setState({ phase: "streaming", isStreaming: true });

  const result: StreamStartResult = await api.streamStart(projectPath, { prompt });
  sseJobId = result.job_id;
  useDispatchManager.setState({
    jobId: result.job_id,
    statusText: result.message,
    progressPct: Math.max(useDispatchManager.getState().progressPct, 8),
  });

  return new Promise<boolean>((resolve, reject) => {
    let settled = false;
    let receivedComplete = false;
    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      fn();
    };

    const streamUrl = `${API_BASE_URL}/api/dispatch/stream/${encodeURIComponent(result.job_id)}`;
    const es = new EventSource(streamUrl);
    eventSource = es;

    es.onopen = () => {
      useDispatchManager.setState({
        isStreaming: true,
        statusText: "Stream connected",
      });
    };

    es.onmessage = (event) => {
      try {
        const streamEvent: StreamEvent = JSON.parse(event.data);
        if (streamEvent.type === "complete") receivedComplete = true;
        handleStreamEvent(streamEvent, () => settle(() => resolve(true)));
      } catch (e) {
        console.error("Failed to parse stream event:", e, event.data);
      }
    };

    es.onerror = (error) => {
      console.error("EventSource error:", error);
      if (es.readyState === EventSource.CLOSED) {
        if (receivedComplete) {
          // Clean close after completion — SSE handled it
          settle(() => resolve(true));
        } else {
          // Connection dropped without completion — fall back to polling
          closeEventSource();
          settle(() => reject(new Error("Stream closed without completion. Falling back to polling.")));
        }
        return;
      }
      closeEventSource();
      settle(() => reject(new Error("Stream connection lost. Falling back to polling.")));
    };
  });
}

function handleStreamEvent(
  event: StreamEvent,
  onComplete: () => void
): void {
  const state = useDispatchManager.getState();

  switch (event.type) {
    case "start":
      useDispatchManager.setState({
        statusText: "Connected to dispatch stream",
        progressPct: Math.max(state.progressPct, 10),
      });
      break;

    case "status":
      useDispatchManager.setState({
        statusText: event.data,
        progressPct: event.data.includes("processing")
          ? Math.max(state.progressPct, 30)
          : state.progressPct,
      });
      break;

    case "output": {
      const newLines = [...state.streamOutputLines, event.data].slice(-1000);
      useDispatchManager.setState({
        streamSequence: Math.max(state.streamSequence, event.sequence),
        streamOutputLines: newLines,
        outputTail: newLines.slice(-24).join("\n"),
      });
      break;
    }

    case "error":
      useDispatchManager.setState({ errorDetail: event.data });
      break;

    case "complete":
      handleStreamCompletion(event.data as StreamCompletionStatus);
      onComplete();
      break;
  }
}

async function handleStreamCompletion(
  status: StreamCompletionStatus
): Promise<void> {
  const state = useDispatchManager.getState();
  const output = state.streamOutputLines.join("\n");

  switch (status) {
    case "success": {
      // Milestone plan-phase interception: transition to review instead of full completion
      if (state.milestonePlanPhase === "planning") {
        const planOutput = state.streamOutputLines.join("\n") || "";
        useDispatchManager.getState().completePlanPhase(planOutput);
        completeDispatch();
        toast.success("Plan Generated", "Review the plan and choose how to execute.");
        return;
      }

      const dispatchContext = state.lastContext;
      completeDispatch();

      if (dispatchContext?.itemRef?.text && projectPathRef) {
        try {
          await api.toggleRoadmapItem(
            projectPathRef,
            dispatchContext.itemRef.text
          );
          toast.success(
            "Task Completed",
            `Marked "${dispatchContext.itemRef.text}" as done`
          );
        } catch (error) {
          console.error("Failed to auto-mark task as done:", error);
          toast.success(
            "Dispatch Successful",
            "Claude Code completed the task."
          );
        }
      } else {
        toast.success(
          "Dispatch Successful",
          "Claude Code completed the task."
        );
      }
      break;
    }

    case "token_limit":
      triggerFallback(
        state.lastContext?.prompt || "",
        output || null,
        "Claude Code token limit reached"
      );
      toast.warning(
        "Claude Code limit reached",
        "Select Codex or Gemini to run this task."
      );
      break;

    case "cancelled":
      cancelDispatch();
      toast.info("Dispatch Cancelled", "Job cancelled.");
      break;

    case "failed":
    default:
      failDispatch(
        state.errorDetail || "Claude Code failed. See details in overlay.",
        output || null,
        null
      );
      toast.error(
        "Dispatch Failed",
        state.errorDetail || "Claude Code failed. See details in overlay."
      );
      break;
  }
}
