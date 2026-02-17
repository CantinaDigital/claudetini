// ============================================
// Project Types
// ============================================

export interface Project {
  id: string;
  name: string;
  path: string;
  branch: string;
  uncommitted: number;
  lastSession: string | null;
  lastOpened: string | null;
  lastOpenedTimestamp: string | null;
  costWeek: string;
  totalSessions: number;
  readmeSummary?: string | null;
}

export interface HealthReport {
  items: HealthItem[];
  score: number;
}

export interface HealthItem {
  name: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

// ============================================
// Roadmap Types
// ============================================

export interface Roadmap {
  milestones: Milestone[];
  totalItems: number;
  completedItems: number;
  progress: number;
}

export interface Milestone {
  id: number;
  phase: string;
  title: string;
  sprint: string;
  items: MilestoneItem[];
}

export interface MilestoneItem {
  text: string;
  done: boolean;
  prompt?: string;
  context?: string;
}

// ============================================
// Timeline Types
// ============================================

export interface TimelineResponse {
  entries: TimelineEntry[];
  total: number;
}

export interface CommitInfo {
  sha: string;
  message: string;
  timestamp: string;
}

export interface TokenUsageSnapshot {
  inputTokens: number;
  outputTokens: number;
  model: string;
}

export interface SessionTestResult {
  passed: boolean;
  total?: number | null;
  passedCount?: number | null;
  raw?: string | null;
}

export interface TimelineEntry {
  sessionId: string;
  date: string;
  durationMinutes: number;
  summary: string;
  provider?: "claude" | "codex" | "gemini" | string;
  branch?: string | null;
  promptUsed?: string;  // What the user asked - the original prompt
  commits: CommitInfo[];
  filesChanged: number;
  todosCreated: number;
  todosCompleted: number;
  roadmapItemsCompleted: string[];
  costEstimate?: number;
  gateStatuses: Record<string, string>;
  tokenUsage?: TokenUsageSnapshot | null;
  testResults?: SessionTestResult | null;
}

export interface Session {
  id: number;
  date: string;
  time: string;
  duration: string;
  summary: string;
  promptUsed?: string;  // What the user asked - the original prompt
  commits: number;
  filesChanged: number;
  linesAdded: number;
  linesRemoved: number;
  tests?: {
    passed: number;
    failed: number;
    coverage: number;
  };
  branch: string;
  provider: string;
  cost?: string;
  tokens?: number;
  dispatchMode?: string;
}

export interface Commit {
  hash: string;
  msg: string;
  branch: string;
  date: string;
  time: string;
  session?: number;
  merge?: boolean;
}

// ============================================
// Git Types
// ============================================

export interface SubmoduleIssue {
  file: string;
}

export interface GitStatus {
  branch: string;
  unpushed: UnpushedCommit[];
  staged: UncommittedFile[];
  uncommitted: UncommittedFile[];
  untracked: UntrackedFile[];
  stashed: Stash[];
  submodule_issues: SubmoduleIssue[];
}

export interface UnpushedCommit {
  hash: string;
  msg: string;
  time: string;
}

export interface UncommittedFile {
  file: string;
  status: string;
  lines: string | null;
}

export interface UntrackedFile {
  file: string;
}

export interface Stash {
  id: string;
  msg: string;
  time: string;
}

// ============================================
// Quality Gates Types
// ============================================

export interface GateFinding {
  severity: string;
  description: string;
  file?: string;
  line?: number;
}

export interface GateReport {
  gates: Gate[];
  runId: string;
  timestamp: string;
  trigger: string;
  overallStatus: "pass" | "warn" | "fail";
  changedFiles: string[];
}

export interface Gate {
  name: string;
  status: "pass" | "warn" | "fail" | "skipped" | "error";
  message: string;
  detail?: string;
  findings: GateFinding[];
  durationSeconds: number;
  hardStop: boolean;
  costEstimate: number;
}

export interface QualityIssue {
  severity: "pass" | "warn" | "fail";
  title: string;
  suggestion: string;
}

// ============================================
// Logs Types
// ============================================

export interface LogEntry {
  time: string;
  level: "info" | "pass" | "warn" | "fail";
  src: string;
  msg: string;
}

// ============================================
// Settings Types
// ============================================

export interface Provider {
  name: string;
  version: string;
  status: string;
  color: string;
}

export interface ProviderInfo {
  name: string;
  version: string;
  status: "authenticated" | "not configured" | "error";
  color: string;
  installed: boolean;
}

export interface BranchStrategyInfo {
  detected: string;
  description: string;
  evidence: string;
}

export interface ContextFileInfo {
  file: string;
  status: "pass" | "warn" | "missing";
  detail: string;
  icon: string;
}

export interface BudgetInfo {
  monthly: number;
  spent: number;
  weeklySpent: number;
  perSession: number;
}

export interface GateHistoryPoint {
  timestamp: string;
  status: "pass" | "warn" | "fail";
  score: number;
}

// ============================================
// Queued Dispatch Types
// ============================================

export interface QueuedDispatch {
  id: string;
  prompt: string;
  mode: string;
  source: "ask" | "task" | "fix" | "queue";
  itemRef?: { text: string; prompt?: string };
  queuedAt: number;
}

// ============================================
// Dispatch Types
// ============================================

export interface DispatchResult {
  success: boolean;
  sessionId?: string;
  error?: string;
  error_code?: string | null;
  output?: string;
  verification?: Record<string, string> | null;
  provider?: "claude" | "codex" | "gemini";
  token_limit_reached?: boolean;
}

export interface DispatchStartResult {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  phase: string;
  message: string;
}

export interface DispatchJobStatus {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  phase: string;
  message: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  done: boolean;
  result?: DispatchResult | null;
  error_detail?: string | null;
  output_tail?: string | null;
  log_file?: string | null;
}

export interface DispatchAdvice {
  estimated_tokens: number;
  estimated_cost?: number | null;
  estimated_effort_units: number;
  usage_mode: "subscription" | "api";
  telemetry_source: string;
  remaining_pct?: number | null;
  should_suggest_fallback: boolean;
  suggested_provider?: "codex" | "gemini" | null;
  reason: string;
}

export interface ProviderUsageTotals {
  tokens: number;
  effort_units: number;
  cost_usd: number;
  events: number;
}

export interface DispatchUsageSummary {
  project_id: string;
  days: number;
  providers: Record<string, ProviderUsageTotals>;
  total_tokens: number;
  total_effort_units: number;
  total_cost_usd: number;
  total_events: number;
  latest_event_at?: string | null;
}

// ============================================
// Status Types
// ============================================

export type Status = "pass" | "warn" | "fail";

// ============================================
// Overview Tab Types
// ============================================

export interface ProjectData {
  name: string;
  summary: string;
  branch: string;
  branchStrategy: string;
  uncommitted: number;
  lastSession: string;
  costWeek: string;
  totalSessions: number;
}

export interface PromptHistoryEntry {
  v: number;
  prompt: string;
  outcome: "pass" | "fail" | null;
  cost: string | null;
  error: string | null;
  date: string | null;
}

export interface RetryChainEntry {
  attempt: number;
  prompt: string;
  outcome: "pass" | "fail";
  error: string;
  date: string;
}

export interface OverviewMilestoneItem {
  text: string;
  done: boolean;
  prompt?: string;
  promptHistory?: PromptHistoryEntry[];
  retryChain?: RetryChainEntry[];
}

export interface OverviewMilestoneData {
  id: number;
  title: string;
  phase: string;
  sprint: string;
  items: OverviewMilestoneItem[];
}

export interface HealthData {
  name: string;
  status: Status;
  detail: string;
}

export interface GateData {
  name: string;
  status: Status;
  detail: string;
}

// ============================================
// Streaming Dispatch Types
// ============================================

export type StreamEventType = "start" | "output" | "status" | "complete" | "error";

export interface StreamEvent {
  type: StreamEventType;
  data: string;
  sequence: number;
  timestamp: string;
  job_id: string;
}

export type StreamCompletionStatus = "success" | "failed" | "cancelled" | "token_limit";

export interface StreamStartResult {
  job_id: string;
  stream_url: string;
  status: "starting" | "running";
  message: string;
}

export interface StreamJobStatus {
  job_id: string;
  is_running: boolean;
  is_cancelled: boolean;
  has_result: boolean;
  result: {
    success: boolean;
    token_limit_reached: boolean;
    cancelled: boolean;
    error_message: string | null;
  } | null;
}

export interface StreamCancelResult {
  success: boolean;
  message: string;
}

// ============================================
// Live Session Types
// ============================================

export interface LiveSession {
  active: boolean;
  sessionId?: string | null;
  provider: string;
  pid?: number | null;
  startedAt?: string | null;
  elapsed?: string | null;
  estimatedCost?: string | null;
  tokensUsed: number;
  filesModified: string[];
  linesAdded: number;
  linesRemoved: number;
}

export interface Exchange {
  time: string;
  type: "user" | "assistant";
  summary: string;
  files?: string[];
  lines?: string | null;
}

export interface LiveSessionResponse {
  active: boolean;
  session?: LiveSession | null;
  sessions?: LiveSession[];
  exchanges: Exchange[];
}

// ============================================
// Reconciliation Types
// ============================================

export interface QuickCheckResponse {
  has_changes: boolean;
  commits_count: number;
  files_modified: number;
  uncommitted_count: number;
}

export interface FileChange {
  path: string;
  change_type: "added" | "modified" | "deleted";
  loc_delta: number;
  is_substantial: boolean;
}

export interface RoadmapSuggestion {
  item_text: string;
  milestone_name: string;
  confidence: number;
  reasoning: string[];
  matched_files: string[];
  matched_commits: string[];
  session_id?: string | null;
}

export interface ReconciliationReport {
  report_id: string;
  timestamp: string;
  old_snapshot_id: string;
  new_snapshot_id: string;
  commits_added: number;
  files_changed: FileChange[];
  dependencies_changed: boolean;
  suggestions: RoadmapSuggestion[];
  already_completed_externally: string[];
  ai_metadata?: {
    candidates_found: number;
    ai_calls_succeeded: number;
    ai_calls_failed: number;
  } | null;
}

export interface AnalysisJobResponse {
  job_id: string;
  status: "started";
}

export interface JobStatusResponse {
  status: "running" | "complete" | "failed";
  progress: number;
  error?: string | null;
}

export interface ApplyReconciliationRequest {
  report_id: string;
  accepted_items: string[];
  dismissed_items: string[];
}

export interface ApplyReconciliationResponse {
  success: boolean;
  items_completed: number;
  items_dismissed: number;
}

export interface Snapshot {
  snapshot_id: string;
  timestamp: string;
  git_head_sha: string | null;
  git_branch: string | null;
  completed_items: number;
  total_items: number;
}

export type ReconciliationFooterState =
  | "hidden"
  | "changes_detected"
  | "analyzing"
  | "report_ready"
  | "no_matches"
  | "baseline_created";

// ============================================
// Readiness Types
// ============================================

export interface ReadinessCheck {
  name: string;
  category: string;
  passed: boolean;
  severity: string;
  weight: number;
  message: string;
  remediation?: string | null;
  why?: string | null;
  can_auto_generate?: boolean;
  details?: Record<string, unknown>;
}

export interface ReadinessReport {
  score: number;
  is_ready: boolean;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  checks: ReadinessCheck[];
  critical_issues: string[];
  warnings: string[];
}

// ============================================
// Milestone Plan Mode Types
// ============================================

export type MilestonePlanPhase = "idle" | "planning" | "reviewing" | "executing" | "complete" | "failed";

export interface MilestonePlanContext {
  milestoneId: number;
  milestoneTitle: string;
  remainingItems: MilestoneItem[];
  combinedPrompt: string;
}

// ============================================
// Parallel Execution Types (AI-Orchestrated)
// ============================================

export type ParallelPhase =
  | "idle"
  | "git_check"
  | "planning"
  | "plan_review"
  | "replanning"
  | "executing"
  | "merging"
  | "verifying"
  | "finalizing"
  | "complete"
  | "failed"
  | "cancelled";

// Planning Agent Types

export interface AgentAssignment {
  agent_id: number;
  theme: string;
  task_indices: number[];
  rationale: string;
}

export interface ExecutionPhase {
  phase_id: number;
  name: string;
  description: string;
  parallel: boolean;
  agents: AgentAssignment[];
}

export interface ExecutionPlan {
  summary: string;
  phases: ExecutionPhase[];
  success_criteria: string[];
  estimated_total_agents: number;
  warnings: string[];
}

export interface CriterionResult {
  criterion: string;
  passed: boolean;
  evidence: string;
  notes: string;
}

export interface VerificationResult {
  overall_pass: boolean;
  criteria_results: CriterionResult[];
  summary: string;
}

// Execution Status Types

export interface AgentSlotStatus {
  task_index: number;
  task_text: string;
  status: string;
  output_tail: string | null;
  error: string | null;
  cost_estimate: number;
  group_id: number;
  phase_id: number;
}

export interface MergeResultStatus {
  branch: string;
  success: boolean;
  conflict_files: string[];
  resolution_method: string;
  message: string;
}

export interface ParallelBatchStatus {
  batch_id: string;
  phase: ParallelPhase;
  current_phase_id: number;
  current_phase_name: string;
  agents: AgentSlotStatus[];
  merge_results: MergeResultStatus[];
  verification: VerificationResult | null;
  verification_output_tail: string | null;
  finalize_message: string | null;
  plan_summary: string;
  total_cost: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

// ============================================
// Intelligence Tab Types
// ============================================

// Hardcoded findings
export interface HardcodedFinding {
  file_path: string;
  line_number: number;
  category: 'url' | 'ip_address' | 'port' | 'todo_marker' | 'placeholder' | 'absolute_path' | 'magic_number' | 'env_reference' | 'doc_drift';
  severity: 'critical' | 'warning' | 'info';
  matched_text: string;
  suggestion: string;
}

export interface HardcodedScanResult {
  findings: HardcodedFinding[];
  scanned_file_count: number;
}

// Dependencies
export interface DependencyPackage {
  name: string;
  current_version: string;
  latest_version: string | null;
  update_severity: 'major' | 'minor' | 'patch' | null;
  ecosystem: 'npm' | 'pip' | 'cargo' | 'go';
  is_dev: boolean;
}

export interface DependencyVulnerability {
  package_name: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  advisory_id: string;
  title: string;
  fixed_in: string | null;
}

export interface DependencyReport {
  ecosystem: string;
  manifest_path: string;
  outdated: DependencyPackage[];
  vulnerabilities: DependencyVulnerability[];
}

// Integrations
export interface IntegrationPoint {
  service_name: string;
  integration_type: 'external_api' | 'internal_route' | 'sdk_import' | 'database';
  file_path: string;
  line_number: number;
  matched_text: string;
  endpoint_url: string | null;
  http_method: string | null;
}

export interface ServiceIntegration {
  service_name: string;
  count: number;
  endpoints: string[];
  files: string[];
}

export interface IntegrationMap {
  integrations: IntegrationPoint[];
  services_detected: ServiceIntegration[];
  files_scanned: number;
}

// Freshness
export interface FileFreshness {
  file_path: string;
  last_modified: string;
  days_since_modified: number;
  commit_count: number;
  category: 'fresh' | 'aging' | 'stale' | 'abandoned';
  last_author: string | null;
}

export interface AgeDistribution {
  fresh: number;
  aging: number;
  stale: number;
  abandoned: number;
}

export interface FreshnessReport {
  files: FileFreshness[];
  age_distribution: AgeDistribution;
  stale_files: FileFreshness[];
  abandoned_files: FileFreshness[];
  single_commit_files: string[];
  freshness_score: number;
}

// Feature inventory
export interface FeatureEntry {
  name: string;
  category: string;
  file_path: string;
  line_number: number;
  framework: string | null;
  loc: number;
  is_exported: boolean;
  import_count?: number;
  roadmap_match?: string;
}

export interface FeatureInventory {
  features: FeatureEntry[];
  by_category: Record<string, number>;
  roadmap_mappings: Record<string, string>;
  untracked_features: Array<{ feature: FeatureEntry; reason: string }>;
  total_features: number;
  most_coupled: Array<{ name: string; import_count: number; files_importing: string[] }>;
  import_counts: Record<string, number>;
}

// Intelligence report
export interface CategoryScore {
  category: string;
  score: number;
  grade: string;
  finding_count: number;
  critical_count: number;
  warning_count: number;
}

export interface IntelligenceSummary {
  total_findings: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
}

export interface IntelligenceReport {
  project_path: string;
  generated_at: string;
  overall_score: number;
  grade: string;
  hardcoded: HardcodedScanResult;
  dependencies: DependencyReport[];
  integrations: IntegrationMap;
  freshness: FreshnessReport;
  features: FeatureInventory;
  summary: IntelligenceSummary;
  top_issues: Array<{ issue: string; severity: string; file_path?: string }>;
  scan_duration_ms: number;
  scans_completed: number;
  scans_failed: number;
}


