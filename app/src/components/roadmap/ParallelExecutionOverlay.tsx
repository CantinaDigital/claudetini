import { useMemo, useState } from "react";
import { t } from "../../styles/tokens";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { useParallelManager } from "../../managers/parallelManager";

/** Extract display title from task text. Splits on em-dash separator if present. */
function displayTitle(text: string): string {
  const idx = text.indexOf(" \u2014 ");
  if (idx > 0 && idx < 120) return text.substring(0, idx);
  return text;
}

interface ParallelExecutionOverlayProps {
  projectPath: string;
}

const PHASE_STEPS: { key: string; label: string }[] = [
  { key: "planning", label: "Plan" },
  { key: "plan_review", label: "Review" },
  { key: "executing", label: "Execute" },
  { key: "verifying", label: "Verify" },
  { key: "finalizing", label: "Finalize" },
];

function statusIcon(status: string): React.ReactNode {
  switch (status) {
    case "running":
      return (
        <div className="w-3 h-3 border-[1.5px] border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
      );
    case "succeeded":
      return <Icons.check size={10} color={t.green} />;
    case "failed":
      return <span className="text-[10px] text-mc-red">&#10007;</span>;
    case "cancelled":
      return <span className="text-[10px] text-mc-text-3">&#8212;</span>;
    default:
      return <div className="w-2 h-2 rounded-full bg-mc-surface-3" />;
  }
}

const PHASE_COLORS = [
  "border-mc-accent-border bg-mc-accent-muted",
  "border-mc-green-border bg-mc-green-muted",
  "border-mc-cyan-border bg-mc-cyan-muted",
  "border-mc-amber-border bg-mc-amber-muted",
];

export function ParallelExecutionOverlay({ projectPath }: ParallelExecutionOverlayProps) {
  const showOverlay = useParallelManager((s) => s.showOverlay);
  const phase = useParallelManager((s) => s.phase);
  const milestoneTitle = useParallelManager((s) => s.milestoneTitle);
  const tasks = useParallelManager((s) => s.tasks);
  const error = useParallelManager((s) => s.error);
  const plan = useParallelManager((s) => s.plan);
  const planOutputTail = useParallelManager((s) => s.planOutputTail);
  const agents = useParallelManager((s) => s.agents);
  const mergeResults = useParallelManager((s) => s.mergeResults);
  const totalCost = useParallelManager((s) => s.totalCost);
  const currentPhaseName = useParallelManager((s) => s.currentPhaseName);
  const currentPhaseId = useParallelManager((s) => s.currentPhaseId);
  const verification = useParallelManager((s) => s.verification);
  const verificationOutputTail = useParallelManager((s) => s.verificationOutputTail);
  const finalizeMessage = useParallelManager((s) => s.finalizeMessage);
  const userFeedback = useParallelManager((s) => s.userFeedback);

  // Git dirty state
  const isDirty = useParallelManager((s) => s.isDirty);
  const dirtyFiles = useParallelManager((s) => s.dirtyFiles);
  const commitMessage = useParallelManager((s) => s.commitMessage);
  const isGeneratingMessage = useParallelManager((s) => s.isGeneratingMessage);
  const isCommitting = useParallelManager((s) => s.isCommitting);
  const commitError = useParallelManager((s) => s.commitError);

  // Actions
  const approvePlan = useParallelManager((s) => s.approvePlan);
  const replan = useParallelManager((s) => s.replan);
  const cancel = useParallelManager((s) => s.cancel);
  const closeOverlay = useParallelManager((s) => s.closeOverlay);
  const setUserFeedback = useParallelManager((s) => s.setUserFeedback);
  const setCommitMessage = useParallelManager((s) => s.setCommitMessage);
  const generateCommitMessage = useParallelManager((s) => s.generateCommitMessage);
  const commitAndProceed = useParallelManager((s) => s.commitAndProceed);

  // Collapsible sections
  const [showAllCriteria, setShowAllCriteria] = useState(false);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [collapsedPhases, setCollapsedPhases] = useState<Set<number>>(new Set());

  const isTerminal = phase === "complete" || phase === "failed" || phase === "cancelled";
  const isGitCheck = phase === "git_check";
  const isPlanning = phase === "planning" || phase === "replanning";
  const isReviewing = phase === "plan_review";
  const isExecuting = phase === "executing" || phase === "merging";

  const progressPct = useMemo(() => {
    if (agents.length === 0) return 0;
    const done = agents.filter(
      (a) => a.status === "succeeded" || a.status === "failed" || a.status === "cancelled"
    ).length;
    return Math.round((done / agents.length) * 100);
  }, [agents]);

  const phaseGroups = useMemo(() => {
    if (!plan || agents.length === 0) return [];

    return plan.phases.map((exPhase) => {
      const phaseAgents = agents.filter((a) => a.phase_id === exPhase.phase_id);

      // Group by group_id (agent assignment) within the phase
      const agentGroups = new Map<number, typeof agents>();
      phaseAgents.forEach((a) => {
        if (!agentGroups.has(a.group_id)) agentGroups.set(a.group_id, []);
        agentGroups.get(a.group_id)!.push(a);
      });

      const doneCount = phaseAgents.filter(
        (a) => a.status === "succeeded" || a.status === "failed" || a.status === "cancelled"
      ).length;
      const totalCount = phaseAgents.length;
      const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

      // Phase visual state
      let phaseStatus: "done" | "active" | "pending";
      if (doneCount === totalCount && totalCount > 0) {
        phaseStatus = "done";
      } else if (exPhase.phase_id === currentPhaseId) {
        phaseStatus = "active";
      } else if (exPhase.phase_id < currentPhaseId) {
        phaseStatus = "done"; // past phase
      } else {
        phaseStatus = "pending";
      }

      return {
        phaseId: exPhase.phase_id,
        name: exPhase.name,
        parallel: exPhase.parallel,
        phaseAgentAssignments: exPhase.agents,
        agentGroups,
        allSlots: phaseAgents,
        doneCount,
        totalCount,
        progressPct: pct,
        phaseStatus,
      };
    });
  }, [agents, plan, currentPhaseId]);

  if (!showOverlay) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-[3px]" />

      {/* Overlay panel */}
      <div className="relative bg-mc-surface-0 border border-mc-border-1 rounded-xl shadow-2xl w-[720px] max-h-[90vh] overflow-hidden flex flex-col animate-fade-in">
        {/* Header */}
        <div className="px-5 pt-5 pb-3 border-b border-mc-border-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-mc-accent-muted border border-mc-accent-border flex items-center justify-center">
                {isTerminal ? (
                  phase === "complete" ? (
                    <Icons.check size={12} color={t.green} />
                  ) : (
                    <span className="text-[11px] text-mc-red">&#10007;</span>
                  )
                ) : (
                  <div className="w-3.5 h-3.5 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
                )}
              </div>
              <div>
                <h2 className="text-sm font-bold text-mc-text-0">
                  Parallel Execution{milestoneTitle ? `: ${milestoneTitle}` : ""}
                </h2>
                <p className="text-[10px] text-mc-text-3 font-mono mt-px">
                  {plan ? `${plan.estimated_total_agents} agent(s)` : `${tasks.length} task(s)`} · {phase}
                </p>
              </div>
            </div>
            {isTerminal && (
              <Button small onClick={() => closeOverlay(projectPath)}>Close</Button>
            )}
          </div>

          {/* Phase stepper — hidden during git_check since it's a pre-step */}
          {!isGitCheck && (
            <div className="flex items-center gap-1 mt-3">
              {PHASE_STEPS.map((step, i) => {
                const currentStepPhases: Record<string, string[]> = {
                  planning: ["planning", "replanning"],
                  plan_review: ["plan_review"],
                  executing: ["executing", "merging"],
                  verifying: ["verifying"],
                  finalizing: ["finalizing", "complete"],
                };
                const isActive = currentStepPhases[step.key]?.includes(phase) || false;
                const stepOrderIdx = PHASE_STEPS.findIndex((s) => s.key === step.key);
                const currentOrderIdx = PHASE_STEPS.findIndex((s) => currentStepPhases[s.key]?.includes(phase));
                const isDone = currentOrderIdx > stepOrderIdx || phase === "complete";

                return (
                  <div key={step.key} className="flex items-center gap-1 flex-1">
                    <div className="flex flex-col items-center flex-1 gap-0.5">
                      <span className="text-[9px] text-mc-text-3 font-mono">{step.label}</span>
                      <div
                        className={`h-1 w-full rounded-sm ${
                          isDone
                            ? "bg-mc-green"
                            : isActive
                              ? "bg-mc-accent"
                              : "bg-mc-surface-3"
                        }`}
                      />
                    </div>
                    {i < PHASE_STEPS.length - 1 && <div className="w-px" />}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* Error banner */}
          {error && !isGitCheck && (
            <div className="bg-mc-red-muted border border-mc-red-border rounded-lg p-3 mb-4 text-xs text-mc-red">
              {error}
            </div>
          )}

          {/* Phase: Git Check — focused commit UI */}
          {isGitCheck && isDirty && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-5 h-5 rounded-full bg-mc-amber-muted border border-mc-amber-border flex items-center justify-center">
                  <span className="text-[10px] text-mc-amber">!</span>
                </div>
                <h3 className="text-sm font-semibold text-mc-text-0">
                  Uncommitted Changes
                </h3>
              </div>
              <p className="text-xs text-mc-text-2 mb-3">
                {dirtyFiles.length} tracked file(s) have uncommitted changes. Commit before parallel execution can start.
              </p>

              {/* Dirty file list */}
              <div className="bg-mc-surface-1 border border-mc-border-0 rounded-lg p-3 mb-4 max-h-[150px] overflow-y-auto">
                {dirtyFiles.map((file, i) => (
                  <div key={i} className="text-[10px] font-mono text-mc-text-2 py-0.5">
                    {file}
                  </div>
                ))}
              </div>

              {/* Commit error */}
              {commitError && (
                <div className="bg-mc-red-muted border border-mc-red-border rounded-lg p-2 mb-3 text-[11px] text-mc-red">
                  {commitError}
                </div>
              )}

              {/* Commit form */}
              <textarea
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="Commit message..."
                className="w-full bg-mc-surface-1 border border-mc-border-1 rounded-md text-[11px] text-mc-text-1 p-2 resize-none h-[60px] font-mono placeholder:text-mc-text-3 focus:outline-none focus:border-mc-accent-border"
              />
              <div className="flex gap-2 mt-2">
                <Button
                  small
                  onClick={() => generateCommitMessage(projectPath)}
                  disabled={isGeneratingMessage}
                  className={isGeneratingMessage ? "!bg-mc-surface-2 !border-mc-accent-border !text-mc-accent !opacity-100" : ""}
                >
                  {isGeneratingMessage ? "Generating ✨" : "⚡ AI Message"}
                </Button>
                <Button
                  primary
                  small
                  onClick={() => commitAndProceed(projectPath)}
                  disabled={isCommitting || !commitMessage.trim()}
                >
                  {isCommitting ? "Committing..." : "Commit & Continue"}
                </Button>
              </div>
            </div>
          )}

          {/* Phase: Git Check — loading (brief flash while checking) */}
          {isGitCheck && !isDirty && (
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
              <span className="text-xs text-mc-text-2">Checking git status...</span>
            </div>
          )}

          {/* Phase: Planning / Replanning */}
          {isPlanning && (
            <div>
              <h3 className="text-[11px] font-bold font-mono text-mc-text-2 uppercase tracking-[0.06em] mb-2">
                {phase === "replanning" ? "Re-planning..." : "Planning Agent"}
              </h3>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-4 h-4 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
                <span className="text-xs text-mc-text-2">Analyzing {tasks.length} tasks...</span>
              </div>
              {planOutputTail && (
                <pre className="text-[10px] text-mc-text-3 font-mono bg-mc-surface-1 border border-mc-border-0 rounded-lg p-3 max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                  {planOutputTail}
                </pre>
              )}
            </div>
          )}

          {/* Phase: Plan Review */}
          {isReviewing && plan && (
            <div>
              {/* Plan summary */}
              <div className="bg-mc-surface-1 border border-mc-border-0 rounded-lg p-3 mb-4">
                <p className="text-xs text-mc-text-1"><InlineMarkdown>{plan.summary}</InlineMarkdown></p>
              </div>

              {/* Phases & Agents */}
              {plan.phases.map((exPhase) => (
                <div
                  key={exPhase.phase_id}
                  className={`rounded-lg border p-3 mb-3 ${PHASE_COLORS[exPhase.phase_id % PHASE_COLORS.length]}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Tag>{exPhase.parallel ? "Parallel" : "Sequential"}</Tag>
                    <span className="text-[11px] font-semibold text-mc-text-0">
                      Phase {exPhase.phase_id + 1}: {exPhase.name}
                    </span>
                  </div>
                  <p className="text-[10px] text-mc-text-2 mb-2"><InlineMarkdown>{exPhase.description}</InlineMarkdown></p>
                  <div className={exPhase.parallel && exPhase.agents.length > 1 ? "grid grid-cols-2 gap-2" : "space-y-2"}>
                    {exPhase.agents.map((agent) => (
                      <div key={agent.agent_id} className="bg-mc-surface-0/50 rounded-md p-2">
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="text-[10px] font-bold text-mc-text-0">
                            Agent {agent.agent_id + 1}
                          </span>
                          <span className="text-[10px] text-mc-text-2">· {agent.theme}</span>
                        </div>
                        <div className="space-y-0.5">
                          {agent.task_indices.map((idx) => (
                            <div key={idx} className="text-[10px] text-mc-text-1 pl-2 truncate">
                              <InlineMarkdown>{displayTitle(tasks[idx]?.text || `Task ${idx + 1}`)}</InlineMarkdown>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {/* Success Criteria — collapsed */}
              {plan.success_criteria.length > 0 && (
                <div className="mb-4">
                  <button
                    onClick={() => setShowAllCriteria(!showAllCriteria)}
                    className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-[0.06em] mb-1.5 flex items-center gap-1 hover:text-mc-text-2 transition-colors"
                  >
                    <span className="text-[8px]">{showAllCriteria ? "▼" : "▶"}</span>
                    Success Criteria ({plan.success_criteria.length})
                  </button>
                  {showAllCriteria && (
                    <div className="space-y-1 mt-1">
                      {plan.success_criteria.map((criterion, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-[10px] text-mc-text-1">
                          <span className="text-mc-green mt-px">&#10003;</span>
                          <InlineMarkdown>{criterion}</InlineMarkdown>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Warnings — collapsed */}
              {plan.warnings.length > 0 && (
                <div className="mb-4">
                  <button
                    onClick={() => setShowAllWarnings(!showAllWarnings)}
                    className="text-[10px] font-bold font-mono text-mc-amber uppercase tracking-[0.06em] mb-1.5 flex items-center gap-1 hover:text-mc-amber/80 transition-colors"
                  >
                    <span className="text-[8px]">{showAllWarnings ? "▼" : "▶"}</span>
                    Warnings ({plan.warnings.length})
                  </button>
                  {showAllWarnings && (
                    <div className="space-y-1 mt-1">
                      {plan.warnings.map((warning, i) => (
                        <div
                          key={i}
                          className="bg-mc-amber-muted border border-mc-amber-border rounded-md px-3 py-2 text-[11px] text-mc-amber"
                        >
                          <InlineMarkdown>{warning}</InlineMarkdown>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Feedback textarea for re-planning */}
              <div className="mb-4">
                <h3 className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-[0.06em] mb-1.5">
                  Refine Plan
                </h3>
                <textarea
                  value={userFeedback}
                  onChange={(e) => setUserFeedback(e.target.value)}
                  placeholder="e.g., Group tasks 7-12 together instead, run tests last..."
                  className="w-full bg-mc-surface-1 border border-mc-border-1 rounded-md text-[11px] text-mc-text-1 p-2 resize-none h-[50px] placeholder:text-mc-text-3 focus:outline-none focus:border-mc-accent-border"
                />
              </div>
            </div>
          )}

          {/* Phase: Executing */}
          {isExecuting && (
            <div>
              {/* Phase-grouped execution view */}
              {phaseGroups.length > 0 ? (
                <>
                  {phaseGroups.map((pg) => {
                    const isPending = pg.phaseStatus === "pending";
                    const isActive = pg.phaseStatus === "active";
                    const isDone = pg.phaseStatus === "done";

                    const isExpanded = (() => {
                      if (isPending) return false;
                      if (isActive) return !collapsedPhases.has(pg.phaseId);
                      return collapsedPhases.has(pg.phaseId); // done: default closed
                    })();

                    const toggleCollapse = () => {
                      setCollapsedPhases((prev) => {
                        const next = new Set(prev);
                        if (next.has(pg.phaseId)) next.delete(pg.phaseId);
                        else next.add(pg.phaseId);
                        return next;
                      });
                    };

                    return (
                      <div
                        key={pg.phaseId}
                        className={`rounded-lg border p-3 mb-3 transition-opacity ${
                          PHASE_COLORS[pg.phaseId % PHASE_COLORS.length]
                        } ${isPending ? "opacity-40" : ""}`}
                      >
                        {/* Phase header — clickable to toggle */}
                        <button
                          onClick={!isPending ? toggleCollapse : undefined}
                          className="w-full flex items-center gap-2 text-left"
                          disabled={isPending}
                        >
                          <span className="text-[8px] text-mc-text-3">
                            {isPending ? "▶" : isExpanded ? "▼" : "▶"}
                          </span>
                          <Tag>{pg.parallel ? "Parallel" : "Sequential"}</Tag>
                          <span className="text-[11px] font-semibold text-mc-text-0 flex-1">
                            Phase {pg.phaseId + 1}: {pg.name}
                          </span>
                          {isDone && !isExpanded && (
                            <span className="text-[10px] font-mono text-mc-green">
                              {pg.doneCount}/{pg.totalCount} done
                            </span>
                          )}
                          {isActive && (
                            <span className="text-[10px] font-mono text-mc-accent">
                              {pg.doneCount}/{pg.totalCount}
                            </span>
                          )}
                          {isPending && (
                            <span className="text-[10px] font-mono text-mc-text-3">pending</span>
                          )}
                        </button>

                        {/* Per-phase progress bar */}
                        {!isPending && (
                          <div className="mt-2">
                            <div className="h-1 bg-mc-surface-2 rounded-sm overflow-hidden">
                              <div
                                className={`h-full rounded-sm transition-all duration-500 ${
                                  isDone
                                    ? "bg-mc-green"
                                    : "bg-gradient-to-r from-mc-green to-mc-accent"
                                }`}
                                style={{ width: `${pg.progressPct}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {/* Expanded agent cards */}
                        {isExpanded && (
                          <div
                            className={`mt-3 ${
                              pg.parallel && pg.agentGroups.size > 1
                                ? "grid grid-cols-2 gap-2"
                                : "space-y-2"
                            }`}
                          >
                            {Array.from(pg.agentGroups.entries()).map(([groupId, groupAgents]) => {
                              // Find the agent theme from plan data
                              const assignment = pg.phaseAgentAssignments.find(
                                (a) => a.agent_id === groupId
                              );
                              return (
                                <div
                                  key={groupId}
                                  className="bg-mc-surface-0/50 rounded-md p-2"
                                >
                                  <div className="flex items-center gap-1.5 mb-1">
                                    <span className="text-[10px] font-bold text-mc-text-0">
                                      Agent {groupId + 1}
                                    </span>
                                    {assignment?.theme && (
                                      <span className="text-[10px] text-mc-text-2">
                                        · {assignment.theme}
                                      </span>
                                    )}
                                  </div>
                                  <div className="space-y-1">
                                    {groupAgents.map((agent) => (
                                      <div
                                        key={agent.task_index}
                                        className="flex items-center gap-2"
                                      >
                                        {statusIcon(agent.status)}
                                        <span className="text-[10px] text-mc-text-1 flex-1 truncate">
                                          <InlineMarkdown>{displayTitle(agent.task_text)}</InlineMarkdown>
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {/* Cost display */}
                  {totalCost > 0 && (
                    <div className="text-[10px] font-mono text-mc-text-3 mt-1">
                      Cost: ${totalCost.toFixed(4)}
                    </div>
                  )}
                </>
              ) : (
                /* Fallback: flat agent list when plan is null */
                <>
                  {currentPhaseName && (
                    <h3 className="text-[11px] font-bold font-mono text-mc-text-2 uppercase tracking-[0.06em] mb-3">
                      {currentPhaseName}
                    </h3>
                  )}
                  {(() => {
                    const groups = new Map<number, typeof agents>();
                    agents.forEach((a) => {
                      if (!groups.has(a.group_id)) groups.set(a.group_id, []);
                      groups.get(a.group_id)!.push(a);
                    });
                    return Array.from(groups.entries()).map(([groupId, groupAgents]) => (
                      <div
                        key={groupId}
                        className="rounded-lg border border-mc-border-0 bg-mc-surface-1 p-3 mb-3"
                      >
                        <h4 className="text-[11px] font-semibold text-mc-text-0 mb-2">
                          Agent {groupId + 1}
                        </h4>
                        <div className="space-y-1.5">
                          {groupAgents.map((agent) => (
                            <div key={agent.task_index} className="flex items-center gap-2">
                              {statusIcon(agent.status)}
                              <span className="text-[10px] text-mc-text-1 flex-1 truncate">
                                <InlineMarkdown>{displayTitle(agent.task_text)}</InlineMarkdown>
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ));
                  })()}
                  {/* Fallback progress bar */}
                  <div className="flex items-center gap-2 mt-2">
                    <div className="flex-1 h-1.5 bg-mc-surface-2 rounded-sm overflow-hidden">
                      <div
                        className="h-full rounded-sm bg-gradient-to-r from-mc-green to-mc-accent transition-all duration-500"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-mc-text-2">{progressPct}%</span>
                    {totalCost > 0 && (
                      <span className="text-[10px] font-mono text-mc-text-3">
                        ${totalCost.toFixed(4)}
                      </span>
                    )}
                  </div>
                </>
              )}

              {/* Live terminal output from the currently running agent */}
              {(() => {
                const running = agents.find((a) => a.status === "running");
                if (!running?.output_tail) return null;
                return (
                  <div className="mt-3">
                    <div className="text-[10px] font-mono text-mc-text-3 mb-1">
                      Agent {running.group_id + 1} output:
                    </div>
                    <pre className="text-[10px] text-mc-text-2 font-mono bg-mc-bg border border-mc-border-0 rounded-lg p-3 max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                      {running.output_tail}
                    </pre>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Phase: Verifying */}
          {phase === "verifying" && (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-4 h-4 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
                <span className="text-xs text-mc-text-2">
                  Running verification agent
                  {plan ? ` — checking ${plan.success_criteria.length} criteria` : ""}
                </span>
              </div>
              <p className="text-[10px] text-mc-text-3 mb-3 ml-6">
                Running tests, linting, and checking file integrity...
              </p>

              {/* Live agent output — the actual verification CLI stream */}
              {verificationOutputTail ? (
                <pre className="text-[10px] text-mc-text-2 font-mono bg-mc-bg border border-mc-border-0 rounded-lg p-3 max-h-[350px] overflow-y-auto whitespace-pre-wrap">
                  {verificationOutputTail}
                </pre>
              ) : (
                <div className="bg-mc-surface-1 border border-mc-border-0 rounded-lg p-4 flex items-center justify-center">
                  <span className="text-[10px] text-mc-text-3 font-mono">Waiting for output...</span>
                </div>
              )}
            </div>
          )}

          {/* Phase: Finalizing */}
          {phase === "finalizing" && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-4 h-4 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
                <span className="text-xs text-mc-text-2">Finalizing...</span>
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 text-[10px] text-mc-text-3">
                  <div className="w-3 h-3 border-[1.5px] border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite] shrink-0" />
                  <span>Marking tasks complete in roadmap...</span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-mc-text-3">
                  <div className="w-2 h-2 rounded-full bg-mc-surface-3 shrink-0" />
                  <span>Staging and committing changes...</span>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-mc-text-3">
                  <div className="w-2 h-2 rounded-full bg-mc-surface-3 shrink-0" />
                  <span>Cleaning up worktrees...</span>
                </div>
              </div>
            </div>
          )}

          {/* Phase: Complete */}
          {phase === "complete" && (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Icons.check size={14} color={t.green} />
                <span className="text-sm font-semibold text-mc-text-0">
                  All {agents.length} tasks executed
                </span>
              </div>

              {/* Verification results */}
              {verification && (
                <div className="mb-4">
                  <h3 className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-[0.06em] mb-1.5">
                    Verification Results
                  </h3>
                  <div className="space-y-1">
                    {verification.criteria_results.map((cr, i) => (
                      <div
                        key={i}
                        className={`flex items-start gap-1.5 text-[10px] ${
                          cr.passed ? "text-mc-green" : "text-mc-red"
                        }`}
                      >
                        <span className="mt-px">{cr.passed ? "\u2713" : "\u2715"}</span>
                        <div>
                          <InlineMarkdown className="text-mc-text-1">{cr.criterion}</InlineMarkdown>
                          {!cr.passed && cr.evidence && (
                            <p className="text-mc-text-3 mt-0.5"><InlineMarkdown>{cr.evidence}</InlineMarkdown></p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Merge Results */}
              {mergeResults.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-[10px] font-bold font-mono text-mc-text-3 uppercase tracking-[0.06em] mb-1.5">
                    Merge Results
                  </h3>
                  <div className="space-y-1">
                    {mergeResults.map((mr, i) => (
                      <div
                        key={i}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-md border text-[11px] ${
                          mr.success
                            ? "border-mc-green-border bg-mc-green-muted text-mc-green"
                            : "border-mc-red-border bg-mc-red-muted text-mc-red"
                        }`}
                      >
                        {mr.success ? (
                          <Icons.check size={10} color={t.green} />
                        ) : (
                          <span>&#10007;</span>
                        )}
                        <span className="font-mono text-mc-text-2 flex-1 truncate">{mr.branch}</span>
                        <InlineMarkdown>{mr.message}</InlineMarkdown>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Finalize result */}
              {finalizeMessage && (
                <div className="flex items-center gap-2 mb-4 text-[11px] text-mc-text-2">
                  <Icons.check size={10} color={t.green} />
                  <span className="font-mono">{finalizeMessage}</span>
                </div>
              )}

              {totalCost > 0 && (
                <div className="text-[10px] text-mc-text-3 font-mono">
                  Total cost: ${totalCost.toFixed(4)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-mc-border-0 flex justify-between items-center">
          <div className="text-[10px] text-mc-text-3 font-mono">
            {phase === "complete" && "All done"}
            {phase === "failed" && "Execution failed"}
            {phase === "cancelled" && "Cancelled"}
            {isGitCheck && "Commit required"}
            {isPlanning && "Planning..."}
            {isReviewing && "Review the plan"}
            {isExecuting && (currentPhaseName ? `Phase ${currentPhaseId + 1}: ${currentPhaseName}` : "Running...")}
            {phase === "verifying" && "Verifying..."}
            {phase === "finalizing" && "Finalizing..."}
          </div>
          <div className="flex gap-2">
            {isGitCheck && (
              <Button small className="!text-mc-red !border-mc-red-border" onClick={cancel}>
                Cancel
              </Button>
            )}
            {!isTerminal && !isReviewing && !isGitCheck && (
              <Button small className="!text-mc-red !border-mc-red-border" onClick={cancel}>
                Cancel
              </Button>
            )}
            {isReviewing && (
              <>
                <Button small className="!text-mc-red !border-mc-red-border" onClick={cancel}>
                  Cancel
                </Button>
                {userFeedback.trim() && (
                  <Button small onClick={() => replan(projectPath)}>
                    Re-plan
                  </Button>
                )}
                <Button
                  primary
                  small
                  onClick={() => approvePlan(projectPath)}
                >
                  <Icons.play size={10} /> Approve & Run
                </Button>
              </>
            )}
            {isTerminal && (
              <Button primary small onClick={() => closeOverlay(projectPath)}>
                Done
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
