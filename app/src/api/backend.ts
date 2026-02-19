import type {
  Project,
  TimelineResponse,
  Roadmap,
  GitStatus,
  Commit,
  GateReport,
  HealthReport,
  DispatchResult,
  DispatchStartResult,
  DispatchJobStatus,
  DispatchAdvice,
  DispatchUsageSummary,
  Stash,
  LogEntry,
  StreamStartResult,
  StreamJobStatus,
  StreamCancelResult,
  LiveSessionResponse,
  QuickCheckResponse,
  AnalysisJobResponse,
  JobStatusResponse,
  ReconciliationReport,
  ApplyReconciliationRequest,
  ApplyReconciliationResponse,
  ReadinessReport,
  ProviderInfo,
  BranchStrategyInfo,
  ContextFileInfo,
  BudgetInfo,
  GateHistoryPoint,
  ExecutionPlan,
  ParallelBatchStatus,
  IntelligenceReport,
  CategoryScore,
  ProductMapResponse,
} from "../types";

// Backend API configuration
const API_PORT = 9876;
export const API_BASE_URL = `http://127.0.0.1:${API_PORT}`;

let backendConnected = false;

/**
 * Initialize connection to the Python backend
 * In development, the backend should be started manually with:
 * cd python-sidecar && python -m src.api.server --port 9876
 */
export async function initBackend(): Promise<void> {
  try {
    // Try to connect to the backend
    await waitForHealthy(5);
    backendConnected = true;
    console.log(`Backend connected on port ${API_PORT}`);
  } catch (error) {
    console.warn(
      "Backend not available. Dashboard will show unavailable/empty states until backend is running.\n" +
        "cd python-sidecar && python -m src.api.server --port 9876"
    );
    backendConnected = false;
  }
}

/**
 * Check if backend is connected
 */
export function isBackendConnected(): boolean {
  return backendConnected;
}

/**
 * Stop the Python backend (no-op in dev mode)
 */
export async function stopBackend(): Promise<void> {
  backendConnected = false;
}

/**
 * Wait for the backend health check to pass
 */
async function waitForHealthy(maxAttempts = 10): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        const data = await response.json();
        if (data.status === "ok") {
          return;
        }
      }
    } catch {
      // Server not ready yet
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Backend failed to become healthy");
}

// ── API Performance Timing ──────────────────────────────────────────
// Collects per-request timing and prints a grouped summary once the
// initial burst of requests settles. Open DevTools → Console to see it.
const _apiTimings: { endpoint: string; method: string; ms: number; ok: boolean }[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;

function _recordTiming(endpoint: string, method: string, ms: number, ok: boolean) {
  _apiTimings.push({ endpoint, method, ms, ok });

  // Flush after 2s of quiet (initial burst settles)
  if (_flushTimer) clearTimeout(_flushTimer);
  _flushTimer = setTimeout(() => {
    if (_apiTimings.length === 0) return;

    const sorted = [..._apiTimings].sort((a, b) => b.ms - a.ms);
    const total = sorted.reduce((s, t) => s + t.ms, 0);

    console.groupCollapsed(
      `%c⏱ API Timing: ${sorted.length} calls, ${total}ms total (wall clock lower due to parallelism)`,
      "color: #8b7cf6; font-weight: bold"
    );
    console.table(
      sorted.map((t) => ({
        endpoint: t.endpoint,
        method: t.method,
        ms: t.ms,
        status: t.ok ? "✓" : "✗",
        tier: t.ms < 50 ? "instant" : t.ms < 200 ? "fast" : t.ms < 1000 ? "medium" : "slow",
      }))
    );
    console.groupEnd();

    // Warn on unexpectedly slow calls
    const slow = sorted.filter((t) => t.ms > 500);
    if (slow.length > 0) {
      console.warn(
        `⚠️ ${slow.length} slow API call(s) (>500ms):`,
        slow.map((t) => `${t.endpoint} → ${t.ms}ms`).join(", ")
      );
    }

    _apiTimings.length = 0;
  }, 2000);
}

// ── In-flight GET deduplication ─────────────────────────────────────
// When multiple components request the same GET endpoint concurrently,
// return the existing in-flight promise instead of firing a duplicate request.
const _inflightGets = new Map<string, Promise<unknown>>();

/**
 * Internal fetch implementation with timing instrumentation.
 */
async function _doFetch<T>(
  url: string,
  endpoint: string,
  options?: RequestInit & { timeoutMs?: number }
): Promise<T> {
  const { timeoutMs, ...fetchOptions } = options || {};
  const method = fetchOptions?.method || "GET";
  const t0 = performance.now();
  let response: Response;

  // Set up abort controller for timeout
  const controller = new AbortController();
  const timeout = timeoutMs || 120000; // Default 2 minutes
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions?.headers,
      },
    });
  } catch (error) {
    clearTimeout(timeoutId);
    const ms = Math.round(performance.now() - t0);
    _recordTiming(endpoint, method, ms, false);
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(
        `Request timed out while calling ${endpoint}. The backend may still be processing.`
      );
    }
    if (controller.signal.aborted) {
      throw new Error(
        `Request timed out while calling ${endpoint}. The backend may still be processing.`
      );
    }
    throw new Error(
      `Network request failed for ${endpoint}: ${
        error instanceof Error ? error.message : "Unknown network error"
      }`
    );
  }

  clearTimeout(timeoutId);

  if (!response.ok) {
    const ms = Math.round(performance.now() - t0);
    _recordTiming(endpoint, method, ms, false);
    const errorText = await response.text();
    throw new Error(`API error (${response.status}): ${errorText}`);
  }

  const data = await response.json();
  const ms = Math.round(performance.now() - t0);
  _recordTiming(endpoint, method, ms, true);

  return data;
}

/**
 * Fetch from the backend API with optional timeout.
 * GET requests are deduplicated: concurrent calls to the same URL share one in-flight promise.
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit & { timeoutMs?: number }
): Promise<T> {
  if (!backendConnected) {
    throw new Error("Backend not connected");
  }

  const url = `${API_BASE_URL}${endpoint}`;
  const method = options?.method || "GET";

  // Deduplicate concurrent GET requests to the same URL
  if (method === "GET") {
    const existing = _inflightGets.get(url);
    if (existing) return existing as Promise<T>;

    const promise = _doFetch<T>(url, endpoint, options);
    _inflightGets.set(url, promise);
    // Chain cleanup into the returned promise so we don't create an
    // uncaught derived promise (Safari reports it as Unhandled Rejection)
    return promise.finally(() => _inflightGets.delete(url));
  }

  return _doFetch<T>(url, endpoint, options);
}

/**
 * API methods matching the Python backend routes
 */
export const api = {
  // =====================================
  // Projects
  // =====================================

  listProjects: () => fetchApi<Project[]>("/api/project/list"),

  getProject: (id: string) =>
    fetchApi<Project>(`/api/project/${encodeURIComponent(id)}`),

  registerProject: (path: string) =>
    fetchApi<Project>("/api/project/register", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  getProjectHealth: (id: string) =>
    fetchApi<HealthReport>(`/api/project/health/${encodeURIComponent(id)}`),

  // =====================================
  // Readiness & Bootstrap
  // =====================================

  scanReadiness: (projectPath: string) =>
    fetchApi<ReadinessReport>("/api/readiness/scan", {
      method: "POST",
      body: JSON.stringify({ project_path: projectPath }),
    }),

  startBootstrap: (
    projectPath: string,
    opts: { skipGit?: boolean; skipArchitecture?: boolean; dryRun?: boolean } = {}
  ) =>
    fetchApi<{ session_id: string }>("/api/bootstrap/start", {
      method: "POST",
      body: JSON.stringify({
        project_path: projectPath,
        skip_git: opts.skipGit ?? false,
        skip_architecture: opts.skipArchitecture ?? false,
        dry_run: opts.dryRun ?? false,
      }),
    }),

  estimateBootstrapCost: (projectPath: string) =>
    fetchApi<{ total_tokens: number; input_tokens: number; output_tokens: number; cost_usd: number; steps: number }>(
      "/api/bootstrap/estimate",
      { method: "POST", body: JSON.stringify({ project_path: projectPath }) }
    ),

  // =====================================
  // Timeline
  // =====================================

  getTimeline: (projectId: string, limit = 50) =>
    fetchApi<TimelineResponse>(
      `/api/timeline/${encodeURIComponent(projectId)}?limit=${limit}`
    ),

  // =====================================
  // Git
  // =====================================

  getGitStatus: (projectId: string) =>
    fetchApi<GitStatus>(`/api/git/${encodeURIComponent(projectId)}/status`),

  getCommits: (projectId: string, limit = 30) =>
    fetchApi<Commit[]>(
      `/api/git/${encodeURIComponent(projectId)}/commits?limit=${limit}`
    ),

  getStashes: (projectId: string) =>
    fetchApi<Stash[]>(`/api/git/${encodeURIComponent(projectId)}/stashes`),

  pushToRemote: (projectId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/push`,
      { method: "POST" }
    ),

  commitAll: (projectId: string, message: string) =>
    fetchApi<{ success: boolean; hash?: string; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/commit`,
      {
        method: "POST",
        body: JSON.stringify({ message }),
      }
    ),

  stashPop: (projectId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/stash/pop`,
      { method: "POST" }
    ),

  stashDrop: (projectId: string, stashId?: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/stash/drop`,
      {
        method: "POST",
        body: JSON.stringify({ stash_id: stashId }),
      }
    ),

  generateCommitMessage: (projectId: string) =>
    fetchApi<{ message: string; files: string[]; summary: string }>(
      `/api/git/${encodeURIComponent(projectId)}/generate-message`
    ),

  generateCommitMessageAI: (projectId: string, model?: string) =>
    fetchApi<{ message: string; files: string[]; summary: string; ai_generated: boolean; model?: string; error?: string }>(
      `/api/git/${encodeURIComponent(projectId)}/generate-message-ai${model ? `?model=${encodeURIComponent(model)}` : ""}`
    ),

  quickCommit: (projectId: string) =>
    fetchApi<{
      success: boolean;
      message: string;
      commit_message?: string;
      hash?: string;
      files_committed: number;
    }>(`/api/git/${encodeURIComponent(projectId)}/quick-commit`, {
      method: "POST",
    }),

  stageFiles: (projectId: string, files: string[]) =>
    fetchApi<{ success: boolean; message: string; staged: string[] }>(
      `/api/git/${encodeURIComponent(projectId)}/stage`,
      {
        method: "POST",
        body: JSON.stringify({ files }),
      }
    ),

  stageAll: (projectId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/stage-all`,
      { method: "POST" }
    ),

  unstageFiles: (projectId: string, files: string[]) =>
    fetchApi<{ success: boolean; message: string; unstaged: string[] }>(
      `/api/git/${encodeURIComponent(projectId)}/unstage`,
      {
        method: "POST",
        body: JSON.stringify({ files }),
      }
    ),

  unstageAll: (projectId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/unstage-all`,
      { method: "POST" }
    ),

  commitStaged: (projectId: string, message: string) =>
    fetchApi<{ success: boolean; message: string; hash?: string }>(
      `/api/git/${encodeURIComponent(projectId)}/commit-staged`,
      {
        method: "POST",
        body: JSON.stringify({ message }),
      }
    ),

  discardFile: (projectId: string, file: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/discard`,
      {
        method: "POST",
        body: JSON.stringify({ file }),
      }
    ),

  deleteUntracked: (projectId: string, file: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/git/${encodeURIComponent(projectId)}/untracked`,
      {
        method: "DELETE",
        body: JSON.stringify({ file }),
      }
    ),

  // =====================================
  // Roadmap
  // =====================================

  getRoadmap: (projectId: string) =>
    fetchApi<Roadmap>(`/api/roadmap/${encodeURIComponent(projectId)}`),

  toggleRoadmapItem: (projectId: string, itemText: string) =>
    fetchApi<{ success: boolean; message: string; new_status: boolean }>(
      `/api/roadmap/${encodeURIComponent(projectId)}/toggle-item`,
      {
        method: "POST",
        body: JSON.stringify({ item_text: itemText }),
      }
    ),

  batchToggleRoadmapItems: (
    projectId: string,
    itemTexts: string[],
    markDone = true
  ) =>
    fetchApi<{ success: boolean; toggled_count: number; not_found: string[] }>(
      `/api/roadmap/${encodeURIComponent(projectId)}/batch-toggle`,
      {
        method: "POST",
        body: JSON.stringify({ item_texts: itemTexts, mark_done: markDone }),
      }
    ),

  // =====================================
  // Quality Gates
  // =====================================

  getGateResults: (projectId: string) =>
    fetchApi<GateReport>(`/api/gates/${encodeURIComponent(projectId)}`),

  runGates: (projectId: string) =>
    fetchApi<GateReport>(`/api/gates/${encodeURIComponent(projectId)}/run`, {
      method: "POST",
    }),

  // =====================================
  // Dispatch
  // =====================================

  dispatchStart: (
    projectId: string,
    options: { prompt: string; mode?: string; flags?: string }
  ) =>
    fetchApi<DispatchStartResult>("/api/dispatch/start", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        prompt: options.prompt,
        mode: options.mode,
        flags: options.flags,
      }),
    }),

  getDispatchStatus: (jobId: string) =>
    fetchApi<DispatchJobStatus>(`/api/dispatch/status/${encodeURIComponent(jobId)}`),

  cancelDispatch: (jobId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/dispatch/cancel/${encodeURIComponent(jobId)}`,
      { method: "POST" }
    ),

  readDispatchOutput: (sessionId: string) =>
    fetchApi<{
      lines: string[];
      exists: boolean;
      line_count: number;
    }>(`/api/dispatch/output/${encodeURIComponent(sessionId)}`),

  enrichPrompt: (
    projectId: string,
    taskText: string,
    customPrompt?: string
  ) =>
    fetchApi<{
      enriched_prompt: string;
      context_added: string[];
    }>("/api/dispatch/enrich-prompt", {
      method: "POST",
      body: JSON.stringify({
        project_path: projectId,
        task_text: taskText,
        custom_prompt: customPrompt,
      }),
    }),

  generateTaskPrompt: (projectPath: string, taskText: string) =>
    fetchApi<{ prompt: string; ai_generated: boolean; error?: string }>(
      "/api/dispatch/generate-task-prompt",
      {
        method: "POST",
        body: JSON.stringify({
          project_path: projectPath,
          task_text: taskText,
        }),
      }
    ),

  getDispatchSummary: (sessionId: string, projectPath: string, logFile?: string | null) =>
    fetchApi<{
      success: boolean;
      files_changed: Array<{
        file: string;
        lines_added: number;
        lines_removed: number;
        status: string;
      }>;
      total_added: number;
      total_removed: number;
      summary_message: string | null;
      has_errors: boolean;
    }>("/api/dispatch/summary", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        project_path: projectPath,
        log_file: logFile || undefined,
      }),
    }),

  dispatchFallback: (options: {
    provider: "codex" | "gemini";
    prompt: string;
    projectPath: string;
    cliPath?: string;
  }) =>
    fetchApi<DispatchResult>("/api/dispatch/fallback", {
      method: "POST",
      body: JSON.stringify({
        provider: options.provider,
        prompt: options.prompt,
        project_path: options.projectPath,
        cli_path: options.cliPath,
      }),
      timeoutMs: 930000, // Keep frontend request alive slightly longer than backend CLI timeout (15m)
    }),

  dispatchFallbackStart: (options: {
    provider: "codex" | "gemini";
    prompt: string;
    projectPath: string;
    cliPath?: string;
  }) =>
    fetchApi<DispatchStartResult>("/api/dispatch/fallback/start", {
      method: "POST",
      body: JSON.stringify({
        provider: options.provider,
        prompt: options.prompt,
        project_path: options.projectPath,
        cli_path: options.cliPath,
      }),
    }),

  getDispatchFallbackStatus: (jobId: string) =>
    fetchApi<DispatchJobStatus>(`/api/dispatch/fallback/status/${encodeURIComponent(jobId)}`, {
      timeoutMs: 15000,
    }),

  cancelDispatchFallback: (jobId: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/dispatch/fallback/cancel/${encodeURIComponent(jobId)}`,
      { method: "POST" }
    ),

  dispatchAdvice: (options: {
    prompt: string;
    projectPath: string;
    preferredFallback?: "codex" | "gemini";
    usageMode?: "subscription" | "api";
    claudeRemainingPct?: number;
    fallbackThresholdPct?: number;
  }) =>
    fetchApi<DispatchAdvice>("/api/dispatch/advice", {
      method: "POST",
      body: JSON.stringify({
        prompt: options.prompt,
        project_path: options.projectPath,
        preferred_fallback: options.preferredFallback,
        usage_mode: options.usageMode,
        claude_remaining_pct: options.claudeRemainingPct,
        fallback_threshold_pct: options.fallbackThresholdPct,
      }),
    }),

  getDispatchUsage: (projectId: string, days = 7) =>
    fetchApi<DispatchUsageSummary>(
      `/api/dispatch/usage/${encodeURIComponent(projectId)}?days=${days}`
    ),

  // =====================================
  // Streaming Dispatch
  // =====================================

  streamStart: (projectId: string, options: { prompt: string }) =>
    fetchApi<StreamStartResult>("/api/dispatch/stream/start", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        prompt: options.prompt,
      }),
    }),

  getStreamStatus: (jobId: string) =>
    fetchApi<StreamJobStatus>(
      `/api/dispatch/stream/${encodeURIComponent(jobId)}/status`
    ),

  cancelStream: (jobId: string) =>
    fetchApi<StreamCancelResult>(
      `/api/dispatch/stream/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" }
    ),

  // =====================================
  // Logs
  // =====================================

  getLogs: (projectId: string, limit = 100) =>
    fetchApi<{ entries: LogEntry[]; total_count: number }>(
      `/api/logs/${encodeURIComponent(projectId)}?limit=${limit}`
    ),

  // =====================================
  // Live Sessions
  // =====================================

  getLiveSessions: (projectId: string) =>
    fetchApi<LiveSessionResponse>(`/api/live-sessions/${encodeURIComponent(projectId)}`, {
      timeoutMs: 15000,
    }),

  // =====================================
  // Reconciliation
  // =====================================

  quickCheckChanges: (projectId: string) =>
    fetchApi<QuickCheckResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/quick-check`,
      { timeoutMs: 8000 }
    ),

  startReconciliationAnalysis: (projectId: string, minConfidence?: number) =>
    fetchApi<AnalysisJobResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/analyze`,
      {
        method: "POST",
        body: JSON.stringify({
          min_confidence: minConfidence !== undefined ? minConfidence / 100 : 0.5,
        }),
      }
    ),

  startProgressVerification: (projectId: string, minConfidence?: number) =>
    fetchApi<AnalysisJobResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/verify`,
      {
        method: "POST",
        body: JSON.stringify({
          min_confidence: minConfidence !== undefined ? minConfidence / 100 : 0.5,
        }),
      }
    ),

  startAIProgressVerification: (projectId: string, minConfidence?: number) =>
    fetchApi<AnalysisJobResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/verify-ai`,
      {
        method: "POST",
        body: JSON.stringify({
          min_confidence: minConfidence !== undefined ? minConfidence / 100 : 0.5,
        }),
      }
    ),

  getReconciliationJobStatus: (projectId: string, jobId: string) =>
    fetchApi<JobStatusResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/status/${encodeURIComponent(jobId)}`,
      { timeoutMs: 5000 }
    ),

  getReconciliationResult: (projectId: string, jobId: string) =>
    fetchApi<ReconciliationReport>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/result/${encodeURIComponent(jobId)}`,
      { timeoutMs: 10000 }
    ),

  applyReconciliation: (projectId: string, request: ApplyReconciliationRequest) =>
    fetchApi<ApplyReconciliationResponse>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/apply`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    ),

  getCommitDiff: (projectId: string, commitSha: string) =>
    fetchApi<{ commit_sha: string; diff: string }>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/diff/${encodeURIComponent(commitSha)}`
    ),

  undoReconciliation: (projectId: string) =>
    fetchApi<{ success: boolean; items_reverted: number }>(
      `/api/project/${encodeURIComponent(projectId)}/reconcile/undo`,
      { method: "POST" }
    ),

  // =====================================
  // Providers (detection + testing)
  // =====================================

  detectProviders: (projectPath: string) =>
    fetchApi<ProviderInfo[]>(
      `/api/settings/providers?project_path=${encodeURIComponent(projectPath)}`,
      { timeoutMs: 2000 }
    ),

  testProvider: (providerName: string) =>
    fetchApi<{ success: boolean; message: string; version?: string }>(
      "/api/settings/providers/test",
      {
        method: "POST",
        body: JSON.stringify({ provider: providerName }),
        timeoutMs: 15000,
      }
    ),

  // =====================================
  // Branch Strategy
  // =====================================

  getBranchStrategy: (projectPath: string) =>
    fetchApi<BranchStrategyInfo>(
      `/api/settings/branch-strategy?project_path=${encodeURIComponent(projectPath)}`,
      { timeoutMs: 2000 }
    ),

  // =====================================
  // Context Files
  // =====================================

  getContextFiles: (projectPath: string) =>
    fetchApi<ContextFileInfo[]>(
      `/api/settings/context-files?project_path=${encodeURIComponent(projectPath)}`,
      { timeoutMs: 2000 }
    ),

  generateContextFile: (projectPath: string, filename: string) =>
    fetchApi<{ success: boolean; message: string }>(
      "/api/settings/context-files/generate",
      {
        method: "POST",
        body: JSON.stringify({ project_path: projectPath, filename }),
        timeoutMs: 60000,
      }
    ),

  // =====================================
  // Budget & Usage
  // =====================================

  getBudget: (projectPath: string) =>
    fetchApi<BudgetInfo>(
      `/api/settings/budget?project_path=${encodeURIComponent(projectPath)}`,
      { timeoutMs: 2000 }
    ),

  // =====================================
  // Gate History (for sparkline trends)
  // =====================================

  getGateHistory: (projectPath: string) =>
    fetchApi<Record<string, GateHistoryPoint[]>>(
      `/api/gates/${encodeURIComponent(projectPath)}/history`,
      { timeoutMs: 5000 }
    ),

  // =====================================
  // Settings Actions
  // =====================================

  resetGates: (projectPath: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/gates/${encodeURIComponent(projectPath)}/reset`,
      { method: "POST" }
    ),

  clearHistory: (projectPath: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/project/${encodeURIComponent(projectPath)}/clear-history`,
      { method: "POST" }
    ),

  removeProject: (projectPath: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/project/${encodeURIComponent(projectPath)}/remove`,
      { method: "DELETE" }
    ),

  // =====================================
  // Parallel Execution (AI-Orchestrated)
  // =====================================

  // Git check for parallel execution
  parallelGitCheck: (projectPath: string) =>
    fetchApi<{ clean: boolean; dirty_files: string[] }>("/api/parallel/git-check", {
      method: "POST",
      body: JSON.stringify({ project_path: projectPath }),
    }),

  // Planning
  parallelPlan: (
    projectPath: string,
    tasks: { text: string; prompt?: string }[],
    milestoneTitle = "",
    model?: string
  ) =>
    fetchApi<{ plan_job_id: string; output_file: string }>("/api/parallel/plan", {
      method: "POST",
      body: JSON.stringify({
        project_path: projectPath,
        tasks,
        milestone_title: milestoneTitle,
        model: model || undefined,
      }),
    }),

  parallelPlanStatus: (planJobId: string) =>
    fetchApi<{
      status: string;
      output_tail: string | null;
      plan: ExecutionPlan | null;
      error: string | null;
    }>(`/api/parallel/plan/status/${encodeURIComponent(planJobId)}`),

  parallelReplan: (
    projectPath: string,
    tasks: { text: string; prompt?: string }[],
    previousPlan: ExecutionPlan,
    feedback: string,
    milestoneTitle = "",
    model?: string
  ) =>
    fetchApi<{ plan_job_id: string; output_file: string }>("/api/parallel/plan/replan", {
      method: "POST",
      body: JSON.stringify({
        project_path: projectPath,
        tasks,
        milestone_title: milestoneTitle,
        model: model || undefined,
        previous_plan: previousPlan,
        feedback,
      }),
    }),

  // Execution
  parallelExecute: (
    projectPath: string,
    tasks: { text: string; prompt?: string }[],
    plan: ExecutionPlan,
    maxParallel = 3
  ) =>
    fetchApi<{ batch_id: string; status: string; message: string }>(
      "/api/parallel/execute",
      {
        method: "POST",
        body: JSON.stringify({
          project_path: projectPath,
          tasks,
          plan,
          max_parallel: maxParallel,
        }),
      }
    ),

  parallelExecuteStatus: (batchId: string) =>
    fetchApi<ParallelBatchStatus>(
      `/api/parallel/execute/status/${encodeURIComponent(batchId)}`
    ),

  // Cancel
  parallelCancel: (id: string) =>
    fetchApi<{ success: boolean; message: string }>(
      `/api/parallel/cancel/${encodeURIComponent(id)}`,
      { method: "POST" }
    ),

  // Release HMR lock after parallel execution overlay closes
  parallelReleaseHmrLock: (projectPath: string) =>
    fetchApi<{ released: boolean }>("/api/parallel/release-hmr-lock", {
      method: "POST",
      body: JSON.stringify({ project_path: projectPath }),
    }),

  // =====================================
  // Intelligence
  // =====================================

  scanIntelligence: (projectPath: string, force = false) =>
    fetchApi<IntelligenceReport>(`/api/intelligence/scan${force ? "?force=true" : ""}`, {
      method: "POST",
      body: JSON.stringify({ project_path: projectPath }),
      timeoutMs: 120000,
    }),

  getIntelligence: (projectPath: string) =>
    fetchApi<IntelligenceReport>(
      `/api/intelligence/${encodeURIComponent(projectPath)}`,
      { timeoutMs: 30000 }
    ),

  getIntelligenceSummary: (projectPath: string) =>
    fetchApi<{ score: number; grade: string; categories: CategoryScore[]; staleness_flag: boolean }>(
      `/api/intelligence/summary/${encodeURIComponent(projectPath)}`,
      { timeoutMs: 5000 }
    ),

  scanIntelligenceSingle: (projectPath: string, scannerName: string) =>
    fetchApi<unknown>(
      `/api/intelligence/scan/${encodeURIComponent(scannerName)}`,
      {
        method: "POST",
        body: JSON.stringify({ project_path: projectPath }),
        timeoutMs: 60000,
      }
    ),

  // =====================================
  // Product Map
  // =====================================

  /**
   * Start a product map scan (background job + polling).
   * POST kicks off the scan, then we poll GET /scan/status every 3s.
   * onStatus fires with progress updates so the UI can show a live status.
   * Returns a promise that resolves with the final ProductMapResponse.
   */
  scanProductMap: (
    projectPath: string,
    onStatus?: (msg: string) => void,
    force = false,
  ): { promise: Promise<ProductMapResponse>; abort: () => void } => {
    let aborted = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const promise = (async () => {
      // 1. Kick off the background scan
      const startResp = await fetch(`${API_BASE_URL}/api/product-map/scan${force ? "?force=true" : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_path: projectPath }),
      });
      if (!startResp.ok) {
        const text = await startResp.text();
        throw new Error(`Scan start failed (${startResp.status}): ${text}`);
      }

      onStatus?.("Claude is analyzing your project...");

      // 2. Poll for completion
      const encoded = encodeURIComponent(projectPath);
      return new Promise<ProductMapResponse>((resolve, reject) => {
        const poll = async () => {
          if (aborted) {
            if (timer) clearInterval(timer);
            reject(new Error("Scan aborted"));
            return;
          }
          try {
            const resp = await fetch(
              `${API_BASE_URL}/api/product-map/scan/status?project_path=${encoded}`,
            );
            if (!resp.ok) return; // retry next tick
            const data = await resp.json();

            if (data.progress) onStatus?.(data.progress);

            if (data.status === "done" && data.result) {
              if (timer) clearInterval(timer);
              resolve(data.result as ProductMapResponse);
            } else if (data.status === "error") {
              if (timer) clearInterval(timer);
              reject(new Error(data.error || "Scan failed"));
            }
            // else "running" or "idle" — keep polling
          } catch {
            // Network hiccup — keep polling
          }
        };

        // Poll immediately, then every 3s
        void poll();
        timer = setInterval(poll, 3000);
      });
    })();

    const abort = () => {
      aborted = true;
      if (timer) clearInterval(timer);
    };

    return { promise, abort };
  },

  getProductMap: (projectPath: string) =>
    fetchApi<ProductMapResponse>(
      `/api/product-map/${encodeURIComponent(projectPath)}`,
      { timeoutMs: 10000 }
    ),

  // =====================================
};

export default api;
