import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { Section } from "../ui/Section";
import { Tag } from "../ui/Tag";
import { Button } from "../ui/Button";
import { api, isBackendConnected } from "../../api/backend";
import { toast } from "../ui/Toast";
import { useSettingsStore } from "../../stores/settingsStore";
import { getCached, setCache, invalidateCache } from "../../hooks/useDataCache";
import type { Commit, GitStatus, TimelineEntry, Session } from "../../types";

interface ExtendedSession extends Session {
  sessionId?: string;
}

const EMPTY_GIT_STATUS: GitStatus = {
  branch: "unknown",
  unpushed: [],
  staged: [],
  uncommitted: [],
  untracked: [],
  stashed: [],
  submodule_issues: [],
};

const DISPATCH_MODE_LABELS: Record<string, string> = {
  "with-review": "Review",
  "full-pipeline": "Pipeline",
  "milestone": "Milestone",
};

interface GitTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  onReport?: (sessionId: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}

export function GitTab({ projectPath, isActive = true, onReport, onShowConfirm }: GitTabProps) {
  const [gitStatus, setGitStatus] = useState<GitStatus>(EMPTY_GIT_STATUS);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [loading, setLoading] = useState(true);
  const hasLoaded = useRef(false);

  // Commit message
  const [commitMessage, setCommitMessage] = useState("");
  const [isGeneratingMessage, setIsGeneratingMessage] = useState(false);

  // Action states
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Sessions
  const [sessions, setSessions] = useState<ExtendedSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const selectedSessionRef = useRef(selectedSession);
  selectedSessionRef.current = selectedSession;
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);

  // Map commit hashes to session IDs for correlation highlighting
  const commitSessionMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of timelineEntries) {
      for (const commit of entry.commits) {
        map.set(commit.sha.substring(0, 7), entry.sessionId);
      }
    }
    return map;
  }, [timelineEntries]);

  // ── Helpers ──

  const getStatusBadge = (status: string): { color: string; label: string; bg: string } => {
    const badges: Record<string, { color: string; label: string; bg: string }> = {
      M: { color: t.amber, label: "M", bg: t.amberMuted },
      A: { color: t.green, label: "A", bg: t.greenMuted },
      D: { color: t.red, label: "D", bg: t.redMuted },
      "?": { color: t.cyan, label: "U", bg: "rgba(34,211,238,0.15)" },
    };
    return badges[status] || { color: t.text3, label: "?", bg: t.surface2 };
  };

  const generateBranchColor = (branch: string): string => {
    const normalized = branch.trim().toLowerCase();
    if (!normalized || normalized === "unknown") return t.text3;
    const colors = [t.cyan, t.accent, t.green, t.amber, "#f97316", "#22c55e", "#60a5fa"];
    let hash = 0;
    for (let i = 0; i < normalized.length; i++) {
      hash = normalized.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  const stripBranchPrefix = (branch: string): string =>
    branch.replace(/^feature\//, "").replace(/^fix\//, "").replace(/^hotfix\//, "");

  // ── Data fetching ──

  const fetchGitStatus = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) {
      setGitStatus(EMPTY_GIT_STATUS);
      return;
    }
    const cacheKey = `git:status:${projectPath}`;
    const cached = getCached<GitStatus>(cacheKey);
    if (cached) {
      setGitStatus(cached);
      return;
    }
    try {
      const status = await api.getGitStatus(projectPath);
      setCache(cacheKey, status);
      setGitStatus(status);
    } catch (e) {
      console.warn("Failed to fetch git status:", e);
      setGitStatus(EMPTY_GIT_STATUS);
    }
  }, [projectPath]);

  const fetchCommits = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) {
      setCommits([]);
      return;
    }
    const cacheKey = `commits:${projectPath}`;
    const cached = getCached<Commit[]>(cacheKey);
    if (cached) {
      setCommits(cached);
      return;
    }
    try {
      const data = await api.getCommits(projectPath, 30);
      setCache(cacheKey, data);
      setCommits(data);
    } catch {
      console.warn("Failed to fetch commits");
      setCommits([]);
    }
  }, [projectPath]);

  const fetchSessions = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) {
      setSessions([]);
      setTimelineEntries([]);
      return;
    }

    // Check cache first — sessions/timeline data is mostly immutable
    const cacheKey = `sessions:${projectPath}`;
    const cached = getCached<{ entries: TimelineEntry[]; mapped: ExtendedSession[] }>(cacheKey);
    if (cached) {
      setTimelineEntries(cached.entries);
      setSessions(cached.mapped);
      if (!selectedSessionRef.current && cached.mapped.length > 0) {
        setSelectedSession(cached.mapped[0].sessionId || null);
      }
      return;
    }

    try {
      const timeline = await api.getTimeline(projectPath);
      setTimelineEntries(timeline.entries || []);
      if (timeline.entries && timeline.entries.length > 0) {
        const mapped: ExtendedSession[] = timeline.entries.slice(0, 15).map((entry, i) => {
          const date = new Date(entry.date);
          const totalTokens = entry.tokenUsage
            ? entry.tokenUsage.inputTokens + entry.tokenUsage.outputTokens
            : undefined;
          return {
            id: i + 1,
            sessionId: entry.sessionId,
            date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
            time: date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
            duration:
              entry.durationMinutes >= 60
                ? `${Math.floor(entry.durationMinutes / 60)}h ${entry.durationMinutes % 60}m`
                : `${entry.durationMinutes}m`,
            summary: entry.summary,
            promptUsed: entry.promptUsed,
            commits: entry.commits?.length || 0,
            filesChanged: entry.filesChanged,
            linesAdded: 0,
            linesRemoved: 0,
            branch: entry.branch || "unknown",
            provider: entry.provider || "claude",
            cost: entry.costEstimate ? `$${entry.costEstimate.toFixed(2)}` : undefined,
            tokens: totalTokens,
            tests: entry.testResults
              ? {
                  passed: entry.testResults.passedCount ?? 0,
                  failed: entry.testResults.total
                    ? (entry.testResults.total - (entry.testResults.passedCount ?? 0))
                    : 0,
                  coverage: 0,
                }
              : undefined,
          };
        });
        setSessions(mapped);
        setCache(cacheKey, { entries: timeline.entries, mapped });
        if (!selectedSessionRef.current && mapped.length > 0) {
          setSelectedSession(mapped[0].sessionId || null);
        }
      } else {
        setSessions([]);
      }
    } catch (e) {
      console.warn("Failed to fetch timeline:", e);
      setSessions([]);
    }
  }, [projectPath]);

  const fetchAllData = useCallback(async () => {
    const _t0 = performance.now();
    setLoading(true);
    await Promise.all([fetchGitStatus(), fetchCommits()]);
    setLoading(false);
    console.log(`%c[GitTab] critical data in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
    fetchSessions().catch((err) => console.warn("Failed to fetch sessions:", err));
  }, [fetchGitStatus, fetchCommits, fetchSessions]);

  const refreshData = useCallback(async () => {
    // Bust caches after mutations (commit, push, stash) so we get fresh data
    invalidateCache("git:");
    invalidateCache("commits:");
    await Promise.all([fetchGitStatus(), fetchCommits()]);
  }, [fetchGitStatus, fetchCommits]);

  // Reset hasLoaded on project change
  useEffect(() => { hasLoaded.current = false; }, [projectPath]);

  useEffect(() => {
    if (!isActive && !hasLoaded.current) return;
    hasLoaded.current = true;
    void fetchAllData();
  }, [fetchAllData, isActive]);

  // ── Actions ──

  const handlePush = async () => {
    if (!projectPath) return;
    setActionLoading("push");
    try {
      const result = await api.pushToRemote(projectPath);
      if (result.success) {
        toast.success("Pushed", result.message);
        invalidateCache("git:");
        await fetchGitStatus();
      } else {
        toast.error("Push Failed", result.message);
      }
    } catch (e) {
      toast.error("Push Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCommit = async () => {
    if (!projectPath || !commitMessage.trim()) return;

    const hasChanges =
      gitStatus.uncommitted.length > 0 ||
      gitStatus.untracked.length > 0 ||
      (gitStatus.staged?.length ?? 0) > 0;

    if (!hasChanges) {
      toast.warning("No Changes", "No changes to commit");
      return;
    }

    setActionLoading("commit");
    try {
      await api.stageAll(projectPath);
      const result = await api.commitStaged(projectPath, commitMessage.trim());
      if (result.success) {
        toast.success(
          "Committed",
          `${result.hash}: ${commitMessage.substring(0, 50)}${commitMessage.length > 50 ? "..." : ""}`
        );
        setCommitMessage("");
        await refreshData();
      } else {
        toast.error("Commit Failed", result.message);
      }
    } catch (e) {
      toast.error("Commit Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleGenerateMessage = async () => {
    if (!projectPath) return;
    setIsGeneratingMessage(true);
    try {
      const lightModel = useSettingsStore.getState().lightModel;
      const result = await api.generateCommitMessageAI(projectPath, lightModel);
      setCommitMessage(result.message);
      if (result.ai_generated) {
        toast.success("AI Generated", result.summary || "Commit message generated by Claude");
      } else if (result.error) {
        toast.warning("Using Heuristic", `${result.error}. Generated basic message instead.`);
      }
    } catch (e) {
      toast.error("Generate Failed", e instanceof Error ? e.message : "Failed to generate message");
    } finally {
      setIsGeneratingMessage(false);
    }
  };

  const handleStashPop = async () => {
    if (!projectPath) return;
    setActionLoading("stash-pop");
    try {
      const result = await api.stashPop(projectPath);
      if (result.success) {
        toast.success("Stash Applied", result.message);
        await refreshData();
      } else {
        toast.error("Stash Pop Failed", result.message);
      }
    } catch (e) {
      toast.error("Stash Pop Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleStashDrop = () => {
    if (!projectPath || !onShowConfirm) return;
    onShowConfirm({
      title: "Drop Stash",
      message: "Permanently delete the stashed changes? This cannot be undone.",
      confirmLabel: "Drop",
      danger: true,
      onConfirm: async () => {
        setActionLoading("stash-drop");
        try {
          const result = await api.stashDrop(projectPath);
          if (result.success) {
            toast.info("Stash Dropped", result.message);
            invalidateCache("git:");
            await fetchGitStatus();
          } else {
            toast.error("Stash Drop Failed", result.message);
          }
        } catch (e) {
          toast.error("Stash Drop Failed", e instanceof Error ? e.message : "Unknown error");
        } finally {
          setActionLoading(null);
        }
      },
    });
  };

  // ── Guards ──

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view git data.
      </div>
    );
  }

  // ── Derived data ──

  const workingTreeCount = gitStatus.uncommitted.length + gitStatus.untracked.length;
  const allWorkingFiles = [
    ...gitStatus.uncommitted.map((f) => ({ ...f, tracked: true })),
    ...gitStatus.untracked.map((f) => ({ file: f.file, status: "?", lines: null as string | null, tracked: false })),
  ];

  // ── Render ──

  return (
    <div className="flex flex-col gap-3.5 animate-fade-in">
      {/* Loading indicator */}
      {loading && (
        <div className="flex items-center gap-2 px-1 py-1 text-[11px] text-mc-text-3">
          <div className="h-[2px] w-16 rounded-full bg-mc-surface-2 overflow-hidden">
            <div className="h-full w-1/2 bg-mc-accent rounded-full animate-pulse" />
          </div>
          <span>Fetching git data…</span>
        </div>
      )}
      {/* ═══ Top Strip: 3-column git status ═══ */}
      <div className="grid grid-cols-3 gap-2.5">
        {/* ── Unpushed Commits ── */}
        <Section label={`Unpushed \u00B7 ${gitStatus.unpushed.length}`}>
          <div className="px-3.5 py-2">
            {gitStatus.unpushed.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5 italic">
                All commits pushed
              </div>
            ) : (
              gitStatus.unpushed.slice(0, 6).map((c, i) => (
                <div
                  key={c.hash}
                  className={`flex items-center gap-2 py-1 ${
                    i > 0 ? "border-t border-mc-border-0" : ""
                  }`}
                >
                  <span className="text-[10px] text-mc-cyan font-mono font-semibold w-[54px] shrink-0">
                    {c.hash}
                  </span>
                  <span className="text-[11.5px] text-mc-text-1 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                    {c.msg}
                  </span>
                  <span className="text-[10px] text-mc-text-3 font-mono shrink-0">
                    {c.time}
                  </span>
                </div>
              ))
            )}
            {gitStatus.unpushed.length > 6 && (
              <div className="text-[10px] text-mc-text-3 py-1">
                +{gitStatus.unpushed.length - 6} more
              </div>
            )}
            <Button
              small
              className="mt-2 w-full"
              onClick={handlePush}
              disabled={gitStatus.unpushed.length === 0 || actionLoading === "push"}
            >
              {actionLoading === "push" ? "Pushing..." : "Push All"}
            </Button>
          </div>
        </Section>

        {/* ── Working Tree ── */}
        <Section label={`Working Tree \u00B7 ${workingTreeCount}`}>
          <div className="px-3.5 py-2">
            {allWorkingFiles.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5 italic">
                Working tree clean
              </div>
            ) : (
              allWorkingFiles.slice(0, 8).map((f, i) => {
                const badge = getStatusBadge(f.status);
                return (
                  <div
                    key={f.file}
                    className={`flex items-center gap-2 py-1 ${
                      i > 0 ? "border-t border-mc-border-0" : ""
                    }`}
                  >
                    <span
                      className="text-[9px] font-bold font-mono px-[5px] py-px rounded-sm shrink-0"
                      style={{ color: badge.color, background: badge.bg }}
                    >
                      {badge.label}
                    </span>
                    <span className="text-[11px] text-mc-text-1 font-mono flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                      {f.file}
                    </span>
                    {f.lines && (
                      <span className="text-[10px] text-mc-text-3 font-mono shrink-0">
                        {f.lines}
                      </span>
                    )}
                  </div>
                );
              })
            )}
            {allWorkingFiles.length > 8 && (
              <div className="text-[10px] text-mc-text-3 py-1">
                +{allWorkingFiles.length - 8} more
              </div>
            )}

            {/* Commit form */}
            <div className="mt-2 pt-2 border-t border-mc-border-0">
              <textarea
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="Commit message..."
                rows={commitMessage.includes("\n") ? Math.min(8, commitMessage.split("\n").length + 1) : 2}
                className="w-full px-2 py-1.5 text-[11px] font-mono bg-mc-surface-2 border border-mc-border-1 rounded-md text-mc-text-1 resize-vertical leading-relaxed"
              />
              <div className="flex gap-1.5 mt-1.5">
                <Button
                  small
                  onClick={handleGenerateMessage}
                  disabled={isGeneratingMessage || workingTreeCount === 0}
                  className={`text-[10px] ${isGeneratingMessage ? "!bg-mc-surface-2 !border-mc-accent-border !text-mc-accent !opacity-100" : ""}`}
                >
                  {isGeneratingMessage ? "Generating ✨" : "⚡ Generate AI Git Message"}
                </Button>
                <div className="flex-1" />
                <Button
                  small
                  primary
                  onClick={handleCommit}
                  disabled={
                    !commitMessage.trim() ||
                    actionLoading === "commit" ||
                    workingTreeCount === 0
                  }
                  className="text-[10px]"
                >
                  {actionLoading === "commit" ? "..." : "Commit All"}
                </Button>
              </div>
            </div>
          </div>
        </Section>

        {/* ── Stash ── */}
        <Section label={`Stash \u00B7 ${gitStatus.stashed.length}`}>
          <div className="px-3.5 py-2">
            {gitStatus.stashed.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5 italic">
                No stashes
              </div>
            ) : (
              gitStatus.stashed.map((stash, i) => (
                <div
                  key={stash.id}
                  className={`flex items-center gap-2 py-1 ${
                    i > 0 ? "border-t border-mc-border-0" : ""
                  }`}
                >
                  <span className="text-[11.5px] text-mc-text-2 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                    {stash.msg}
                  </span>
                  <span className="text-[10px] text-mc-text-3 font-mono shrink-0">
                    {stash.time}
                  </span>
                </div>
              ))
            )}
            {gitStatus.stashed.length > 0 && (
              <div className="flex gap-1.5 mt-2">
                <Button
                  small
                  className="flex-1"
                  onClick={handleStashPop}
                  disabled={actionLoading === "stash-pop"}
                >
                  {actionLoading === "stash-pop" ? "..." : "Pop"}
                </Button>
                <Button
                  small
                  className="flex-1"
                  onClick={handleStashDrop}
                  disabled={actionLoading === "stash-drop"}
                >
                  {actionLoading === "stash-drop" ? "..." : "Drop"}
                </Button>
              </div>
            )}
          </div>
        </Section>
      </div>

      {/* ═══ Bottom: Session–Commit Correlation Grid ═══ */}
      <div className="grid grid-cols-2 gap-3.5">
        {/* ── Sessions ── */}
        <Section label="Sessions">
          <div className="py-1 max-h-[500px] overflow-y-auto">
            {sessions.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 px-4 py-6 text-center italic">
                No sessions found
              </div>
            ) : (
              sessions.map((session, i) => {
                const isSelected = session.sessionId === selectedSession;
                const branchColor = generateBranchColor(session.branch);
                const modeLabel =
                  session.dispatchMode && session.dispatchMode !== "standard"
                    ? DISPATCH_MODE_LABELS[session.dispatchMode] || session.dispatchMode
                    : null;

                return (
                  <div
                    key={session.sessionId || session.id}
                    onClick={() => setSelectedSession(session.sessionId || null)}
                    className={`px-4 py-3 cursor-pointer ${
                      isSelected ? "bg-mc-accent-muted" : ""
                    } ${i < sessions.length - 1 ? "border-b border-mc-border-0" : ""}`}
                    style={{
                      borderLeft: isSelected
                        ? `3px solid ${t.accent}`
                        : "3px solid transparent",
                    }}
                  >
                    {/* Top row: id, date, branch, mode, duration */}
                    <div className="flex justify-between items-start mb-1.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`text-[12px] font-bold font-mono ${
                            isSelected ? "text-mc-accent" : "text-mc-text-1"
                          }`}
                        >
                          #{session.id}
                        </span>
                        <span className="text-[10.5px] text-mc-text-3 font-mono">
                          {session.date}
                        </span>
                        <Tag color={branchColor} bg="transparent">
                          {stripBranchPrefix(session.branch)}
                        </Tag>
                        {modeLabel && (
                          <Tag color={t.accent} bg={t.accentMuted}>
                            {modeLabel}
                          </Tag>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-mc-text-3 shrink-0 ml-2">
                        {session.duration}
                      </span>
                    </div>

                    {/* Summary */}
                    <div className="text-[12px] text-mc-text-2 leading-[1.45] mb-2 line-clamp-2">
                      {session.summary || "No summary"}
                    </div>

                    {/* Stats row */}
                    <div className="flex gap-2.5 text-[10px] font-mono text-mc-text-3 flex-wrap">
                      {session.commits > 0 && (
                        <span>{session.commits} commits</span>
                      )}
                      {session.linesAdded > 0 && (
                        <span className="text-mc-green">+{session.linesAdded}</span>
                      )}
                      {session.linesRemoved > 0 && (
                        <span className="text-mc-red">-{session.linesRemoved}</span>
                      )}
                      {session.cost && (
                        <span className="text-mc-accent">{session.cost}</span>
                      )}
                      {session.tokens != null && session.tokens > 0 && (
                        <span className="opacity-50">
                          {(session.tokens / 1000).toFixed(1)}k tok
                        </span>
                      )}
                      {session.tests && (
                        <span className="ml-auto">
                          {session.tests.failed > 0 ? (
                            <span className="text-mc-red">{session.tests.failed} fail</span>
                          ) : session.tests.coverage > 0 ? (
                            <span className="text-mc-green">{session.tests.coverage}% cov</span>
                          ) : session.tests.passed > 0 ? (
                            <span className="text-mc-green">{session.tests.passed} pass</span>
                          ) : null}
                        </span>
                      )}
                    </div>

                    {/* Report link */}
                    {isSelected && onReport && session.sessionId && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onReport(session.sessionId!);
                        }}
                        className="text-[10px] font-mono text-mc-accent bg-transparent border-none cursor-pointer mt-1.5 p-0"
                      >
                        View full report {"\u2192"}
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </Section>

        {/* ── Commits ── */}
        <Section label="Commits">
          <div className="py-1 max-h-[500px] overflow-y-auto">
            {commits.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 px-4 py-6 text-center italic">
                No commits
              </div>
            ) : (
              commits.slice(0, 20).map((commit, i) => {
                const branchColor = generateBranchColor(
                  commit.branch || gitStatus.branch
                );
                const linkedSession = commitSessionMap.get(commit.hash);
                const isLinked = linkedSession === selectedSession && selectedSession != null;

                return (
                  <div
                    key={`${commit.hash}-${i}`}
                    className={`flex items-center gap-2.5 px-4 py-[6px] ${
                      isLinked ? "bg-mc-accent-muted" : ""
                    } ${i < Math.min(commits.length, 20) - 1 ? "border-b border-mc-border-0" : ""}`}
                    style={{ opacity: commit.merge ? 0.5 : 1 }}
                  >
                    {/* Branch dot with glow when linked */}
                    <div
                      className="w-[7px] h-[7px] rounded-full shrink-0"
                      style={{
                        background: branchColor,
                        boxShadow: isLinked
                          ? `0 0 6px ${branchColor}60`
                          : "none",
                      }}
                    />
                    <span
                      className="text-[10px] font-mono font-semibold w-[54px] shrink-0"
                      style={{ color: branchColor }}
                    >
                      {commit.hash}
                    </span>
                    <span
                      className={`text-[11.5px] flex-1 overflow-hidden text-ellipsis whitespace-nowrap ${
                        commit.merge
                          ? "text-mc-text-3 italic"
                          : "text-mc-text-1"
                      }`}
                    >
                      {commit.msg}
                    </span>
                    <span className="text-[10px] text-mc-text-3 font-mono w-[48px] text-right shrink-0">
                      {commit.date}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
