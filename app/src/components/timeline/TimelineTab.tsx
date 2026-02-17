import { useCallback, useEffect, useMemo, useState } from "react";
import { t } from "../../styles/tokens";
import { Section } from "../ui/Section";
import { Tag } from "../ui/Tag";
import { Button } from "../ui/Button";
import { api, isBackendConnected } from "../../api/backend";
import type { Session, Commit, GitStatus, TimelineEntry } from "../../types";

interface ExtendedSession extends Session {
  sessionId?: string;
  startTime?: Date;
  endTime?: Date;
  promptUsed?: string;
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

const dispatchModeLabels: Record<string, string> = {
  standard: "Std",
  "with-review": "Review",
  "full-pipeline": "Pipeline",
};

const generateBranchColor = (branch: string): string => {
  const normalized = branch.trim().toLowerCase();
  if (!normalized || normalized === "unknown") return t.text3;
  // Known branch overrides from design
  if (normalized === "main" || normalized === "master") return "#f97316";
  const colors = [t.cyan, t.accent, t.green, t.amber, "#f97316", "#22c55e", "#60a5fa"];
  let hash = 0;
  for (let i = 0; i < normalized.length; i++) {
    hash = normalized.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

const getStatusBadge = (status: string): { color: string; label: string } => {
  const badges: Record<string, { color: string; label: string }> = {
    M: { color: t.amber, label: "M" },
    A: { color: t.green, label: "A" },
    D: { color: t.red, label: "D" },
  };
  return badges[status] || { color: t.text3, label: "?" };
};

interface TimelineTabProps {
  projectPath?: string | null;
  onReport?: (sessionId: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}

export function TimelineTab({ projectPath, onReport, onShowConfirm }: TimelineTabProps) {
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ExtendedSession[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [gitStatus, setGitStatus] = useState<GitStatus>(EMPTY_GIT_STATUS);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);

  const commitBranchMap = useMemo(
    () => new Map(commits.map((commit) => [commit.hash, commit.branch])),
    [commits]
  );

  const commitSessionMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of timelineEntries) {
      for (const commit of entry.commits) {
        map.set(commit.sha.substring(0, 7), entry.sessionId);
      }
    }
    return map;
  }, [timelineEntries]);

  const fetchGitStatus = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) {
      setGitStatus(EMPTY_GIT_STATUS);
      return;
    }
    try {
      const status = await api.getGitStatus(projectPath);
      setGitStatus(status);
    } catch (e) {
      console.warn("Failed to fetch git status:", e);
      setGitStatus(EMPTY_GIT_STATUS);
    }
  }, [projectPath]);

  const fetchData = useCallback(async () => {
    if (!projectPath || !isBackendConnected()) {
      setSessions([]);
      setCommits([]);
      setTimelineEntries([]);
      setGitStatus(EMPTY_GIT_STATUS);
      setLoading(false);
      return;
    }

    setLoading(true);
    const _t0 = performance.now();
    try {
      await fetchGitStatus();

      let commitData: Commit[] = [];
      try {
        commitData = await api.getCommits(projectPath, 50);
        setCommits(commitData.map((c) => ({
          hash: c.hash,
          msg: c.msg,
          branch: c.branch,
          date: c.date,
          time: c.time,
          merge: c.merge,
        })));
      } catch {
        console.warn("Failed to fetch commits");
        setCommits([]);
      }

      try {
        const timeline = await api.getTimeline(projectPath);
        setTimelineEntries(timeline.entries || []);
        if (timeline.entries && timeline.entries.length > 0) {
          const branchLookup = new Map(commitData.map((c) => [c.hash, c.branch]));
          const mappedSessions: ExtendedSession[] = timeline.entries.map((entry, i) => {
            const date = new Date(entry.date);
            const endTime = new Date(date.getTime() + entry.durationMinutes * 60 * 1000);
            const entryBranch =
              entry.commits
                .map((commit) => branchLookup.get(commit.sha))
                .find((branch): branch is string => Boolean(branch)) ||
              entry.branch ||
              "unknown";
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
              branch: entryBranch,
              provider: entry.provider || "claude",
              cost: entry.costEstimate ? `$${entry.costEstimate.toFixed(2)}` : undefined,
              tokens: entry.tokenUsage ? entry.tokenUsage.inputTokens + entry.tokenUsage.outputTokens : undefined,
              startTime: date,
              endTime,
            };
          });
          setSessions(mappedSessions);
          setSelectedSession(mappedSessions[0]?.sessionId || null);
        } else {
          setSessions([]);
        }
      } catch (e) {
        console.warn("Failed to fetch timeline:", e);
        setTimelineEntries([]);
        setSessions([]);
      }
    } catch (e) {
      console.warn("Failed to fetch data:", e);
    } finally {
      console.log(`%c[TimelineTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
      setLoading(false);
    }
  }, [fetchGitStatus, projectPath]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handlePushAll = async () => {
    if (!projectPath || !isBackendConnected()) return;
    setActionLoading("push");
    setActionError(null);
    try {
      const result = await api.pushToRemote(projectPath);
      if (!result.success) setActionError(result.message);
      await fetchGitStatus();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Push failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCommitAll = async () => {
    if (!projectPath || !isBackendConnected()) return;

    const changedFiles = [
      ...gitStatus.uncommitted.map((f) => f.file),
      ...gitStatus.untracked.map((f) => f.file),
    ];
    const prefix = changedFiles.length === 1 ? "update" : "chore";
    const filesDesc =
      changedFiles.length <= 3
        ? changedFiles.map((f) => f.split("/").pop()).join(", ")
        : `${changedFiles.length} files`;
    const message = `${prefix}: ${filesDesc}`;

    setActionLoading("commit");
    setActionError(null);
    try {
      const result = await api.commitAll(projectPath, message);
      if (!result.success) setActionError(result.message);
      await fetchGitStatus();
      const commitData = await api.getCommits(projectPath, 50);
      setCommits(
        commitData.map((c) => ({
          hash: c.hash,
          msg: c.msg,
          branch: c.branch,
          date: c.date,
          time: c.time,
          merge: c.merge,
        }))
      );
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Commit failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleStashPop = async () => {
    if (!projectPath || !isBackendConnected()) return;
    setActionLoading("stash-pop");
    setActionError(null);
    try {
      const result = await api.stashPop(projectPath);
      if (!result.success) setActionError(result.message);
      await fetchGitStatus();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Stash pop failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleStashDrop = () => {
    if (!projectPath || !isBackendConnected()) return;
    const executeStashDrop = async () => {
      setActionLoading("stash-drop");
      setActionError(null);
      try {
        const result = await api.stashDrop(projectPath);
        if (!result.success) setActionError(result.message);
        await fetchGitStatus();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Stash drop failed");
      } finally {
        setActionLoading(null);
      }
    };

    if (onShowConfirm) {
      onShowConfirm({
        title: "Drop Stash",
        message: "This will permanently delete the stashed changes. This cannot be undone.",
        confirmLabel: "Drop",
        danger: true,
        onConfirm: executeStashDrop,
      });
    } else {
      void executeStashDrop();
    }
  };

  if (loading) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Loading timeline...
      </div>
    );
  }

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view timeline data.
      </div>
    );
  }

  const totalWorkingTree = gitStatus.uncommitted.length + gitStatus.untracked.length;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {actionError && (
        <div className="bg-mc-red-muted border border-mc-red rounded-md px-3 py-2 text-xs text-mc-red flex justify-between items-center">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="bg-transparent border-none text-mc-red cursor-pointer text-sm font-bold"
          >
            x
          </button>
        </div>
      )}

      {/* Git Status Strip -- 3-column grid */}
      <div className="grid grid-cols-3 gap-2.5">
        {/* Unpushed */}
        <Section label={`Unpushed · ${gitStatus.unpushed.length}`}>
          <div className="px-3.5 py-2">
            {gitStatus.unpushed.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5">No unpushed commits</div>
            ) : (
              gitStatus.unpushed.map((c, i) => (
                <div key={c.hash} className={`flex items-center gap-2 py-1 ${i > 0 ? "border-t border-mc-border-0" : ""}`}>
                  <span className="text-[10px] text-mc-cyan font-mono font-semibold w-[54px]">{c.hash}</span>
                  <span className="text-[11.5px] text-mc-text-1 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{c.msg}</span>
                  <span className="text-[10px] text-mc-text-3 font-mono">{c.time}</span>
                </div>
              ))
            )}
            {gitStatus.unpushed.length > 0 && (
              <Button small className="mt-2 w-full" onClick={handlePushAll} disabled={actionLoading === "push"}>
                {actionLoading === "push" ? "Pushing..." : "Push All"}
              </Button>
            )}
          </div>
        </Section>

        {/* Working Tree */}
        <Section label={`Working Tree · ${totalWorkingTree}`}>
          <div className="px-3.5 py-2">
            {totalWorkingTree === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5">Working tree clean</div>
            ) : (
              <>
                {gitStatus.uncommitted.map((f, i) => {
                  const badge = getStatusBadge(f.status);
                  return (
                    <div key={f.file} className={`flex items-center gap-2 py-1 ${i > 0 ? "border-t border-mc-border-0" : ""}`}>
                      <span
                        className="text-[9px] font-bold font-mono px-[5px] py-px rounded-[3px]"
                        style={{ color: badge.color, background: badge.color + "18" }}
                      >
                        {badge.label}
                      </span>
                      <span className="text-[11px] text-mc-text-1 font-mono flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{f.file}</span>
                      {f.lines && <span className="text-[10px] text-mc-text-3 font-mono">{f.lines}</span>}
                    </div>
                  );
                })}
                {gitStatus.untracked.map((f) => (
                  <div key={f.file} className="flex items-center gap-2 py-1 border-t border-mc-border-0">
                    <span className="text-[9px] font-bold font-mono px-[5px] py-px rounded-[3px] text-mc-green bg-mc-green-muted">U</span>
                    <span className="text-[11px] text-mc-text-2 font-mono flex-1">{f.file}</span>
                  </div>
                ))}
              </>
            )}
            {totalWorkingTree > 0 && (
              <Button small className="mt-2 w-full" onClick={handleCommitAll} disabled={actionLoading === "commit"}>
                {actionLoading === "commit" ? "Committing..." : "Commit All"}
              </Button>
            )}
          </div>
        </Section>

        {/* Stash */}
        <Section label={`Stash · ${gitStatus.stashed.length}`}>
          <div className="px-3.5 py-2">
            {gitStatus.stashed.length === 0 ? (
              <div className="text-[11px] text-mc-text-3 py-1.5">No stashes</div>
            ) : (
              gitStatus.stashed.map((stash) => (
                <div key={stash.id} className="flex items-center gap-2 py-1">
                  <span className="text-[11.5px] text-mc-text-2 flex-1">{stash.msg}</span>
                  <span className="text-[10px] text-mc-text-3 font-mono">{stash.time}</span>
                </div>
              ))
            )}
            {gitStatus.stashed.length > 0 && (
              <div className="flex gap-1.5 mt-2">
                <Button small className="flex-1" onClick={handleStashPop} disabled={actionLoading === "stash-pop"}>
                  {actionLoading === "stash-pop" ? "..." : "Pop"}
                </Button>
                <Button small className="flex-1" onClick={handleStashDrop} disabled={actionLoading === "stash-drop"}>
                  {actionLoading === "stash-drop" ? "..." : "Drop"}
                </Button>
              </div>
            )}
          </div>
        </Section>
      </div>

      {/* Session-Commit Grid -- 2-column */}
      <div className="grid grid-cols-2 gap-3.5">
        {/* Sessions Panel */}
        <Section label="Sessions">
          <div className="py-1">
            {sessions.length === 0 && (
              <div className="text-[11px] text-mc-text-3 px-4 py-3">
                No sessions found. Start a Claude Code session in this project to see activity.
              </div>
            )}
            {sessions.map((session, i) => {
              const isSelected = session.sessionId === selectedSession;
              const branchColor = generateBranchColor(session.branch);

              return (
                <div
                  key={session.sessionId || session.id}
                  onClick={() => setSelectedSession(session.sessionId || null)}
                  className={`px-4 py-3 cursor-pointer ${
                    isSelected
                      ? "bg-mc-accent-muted border-l-[3px] border-l-mc-accent"
                      : "border-l-[3px] border-l-transparent"
                  } ${i < sessions.length - 1 ? "border-b border-mc-border-0" : ""}`}
                >
                  {/* Session header row */}
                  <div className="flex justify-between items-start mb-1.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`text-xs font-bold font-mono ${isSelected ? "text-mc-accent" : "text-mc-text-1"}`}>
                        #{session.id}
                      </span>
                      <span className="text-[10.5px] text-mc-text-3 font-mono">{session.date}</span>
                      <Tag color={branchColor} bg="transparent">
                        {session.branch.replace("feature/", "")}
                      </Tag>
                      {session.dispatchMode && session.dispatchMode !== "standard" && (
                        <Tag color="#8b7cf6" bg="rgba(139,124,246,0.12)">
                          {dispatchModeLabels[session.dispatchMode] || session.dispatchMode}
                        </Tag>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-mc-text-3">{session.duration}</span>
                  </div>

                  {/* Summary */}
                  <div className="text-xs text-mc-text-2 leading-[1.45] mb-2">
                    {session.summary || "No summary available"}
                  </div>

                  {/* Stats row */}
                  <div className="flex gap-2.5 text-[10px] font-mono text-mc-text-3 flex-wrap">
                    <span>{session.commits} commits</span>
                    {session.linesAdded !== undefined && <span className="text-mc-green">+{session.linesAdded}</span>}
                    {session.linesRemoved !== undefined && <span className="text-mc-red">-{session.linesRemoved}</span>}
                    {session.cost && <span className="text-mc-accent">{session.cost}</span>}
                    {session.tokens && <span className="opacity-50">{(session.tokens / 1000).toFixed(1)}k tok</span>}
                    {session.tests && (
                      <span className="ml-auto">
                        {session.tests.failed > 0
                          ? <span className="text-mc-red">{session.tests.failed} fail</span>
                          : <span className="text-mc-green">{session.tests.coverage}% cov</span>}
                      </span>
                    )}
                  </div>

                  {/* View report link */}
                  {isSelected && onReport && session.sessionId && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onReport(session.sessionId!);
                      }}
                      className="text-[10px] font-mono text-mc-accent bg-transparent border-none cursor-pointer mt-1.5 p-0"
                    >
                      View full report →
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </Section>

        {/* Commits Panel */}
        <Section label="Commits">
          <div className="py-1">
            {commits.length === 0 && (
              <div className="text-[11px] text-mc-text-3 px-4 py-3">
                No commits found in this repository.
              </div>
            )}
            {commits.map((commit, i) => {
              const branch = commitBranchMap.get(commit.hash) || commit.branch || "unknown";
              const branchColor = generateBranchColor(branch);
              const commitSessionId = commitSessionMap.get(commit.hash);
              const isLinkedToSelected = commitSessionId === selectedSession;

              return (
                <div
                  key={`${commit.hash}-${i}`}
                  className={`flex items-center gap-2.5 px-4 py-1.5 ${
                    isLinkedToSelected ? "bg-mc-accent-muted" : ""
                  } ${i < commits.length - 1 ? "border-b border-mc-border-0" : ""}`}
                  style={{ opacity: commit.merge ? 0.5 : 1 }}
                >
                  <div
                    className="w-[7px] h-[7px] rounded-full shrink-0"
                    style={{
                      background: branchColor,
                      boxShadow: isLinkedToSelected ? `0 0 6px ${branchColor}60` : "none",
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
                      commit.merge ? "text-mc-text-3 italic" : "text-mc-text-1"
                    }`}
                  >
                    {commit.msg}
                  </span>
                  <span className="text-[10px] text-mc-text-3 font-mono w-12 text-right">
                    {commit.date}
                  </span>
                </div>
              );
            })}
          </div>
        </Section>
      </div>
    </div>
  );
}
