import { useEffect, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { Section } from "../ui/Section";
import { Tag } from "../ui/Tag";
import { SeverityTag } from "../ui/SeverityTag";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import { Select } from "../ui/Select";
import { MilestoneCard } from "./MilestoneCard";
import { RecentSessions } from "./RecentSessions";
import { ValidationList } from "./ValidationList";
import { LiveFeed } from "./LiveFeed";
import { AskInput } from "./AskInput";
import { api, isBackendConnected } from "../../api/backend";
import { useSettingsStore } from "../../stores/settingsStore";
import { useDispatchManager, type DispatchContext } from "../../managers/dispatchManager";
import { useReconciliationManager } from "../../managers/reconciliationManager";
import { useProjectManager } from "../../managers/projectManager";
import { toast } from "../ui/Toast";
import { getCached, setCache, invalidateCache } from "../../hooks/useDataCache";
import { SkeletonCard, SkeletonMilestone, SkeletonSession, SkeletonText } from "../ui/SkeletonLoader";
import type {
  DispatchAdvice,
  Status,
  ProjectData,
  OverviewMilestoneItem,
  OverviewMilestoneData,
  HealthData,
  GateData,
  QualityIssue,
  TimelineEntry,
} from "../../types";

function deriveBranchStrategy(branch: string): string {
  return branch === "main" || branch === "master" ? "trunk-based" : "feature-branch";
}

// Session type for RecentSessions component
interface RecentSession {
  id: string;
  summary: string;
  date: string;
  duration: string;
  cost?: string;
  linesAdded: number;
  linesRemoved: number;
  testsPassed: boolean;
  provider?: string;
}

interface OverviewTabProps {
  projectPath?: string | null;
  onStart?: (prompt: string, mode: string) => void;
  onReport?: (sessionId?: string) => void;
  onNavigateToSettings?: () => void;
  onNavigateToGit?: () => void;
  onShowPreFlight?: (
    prompt: string,
    mode: string,
    source?: DispatchContext["source"],
    itemRef?: DispatchContext["itemRef"]
  ) => void;
}

export function OverviewTab({
  projectPath,
  onStart,
  onReport,
  onNavigateToSettings,
  onNavigateToGit,
  onShowPreFlight,
}: OverviewTabProps) {
  const preferredFallback = useSettingsStore((state) => state.preferredFallback);
  const usageMode = useSettingsStore((state) => state.usageMode);
  const claudeRemainingPct = useSettingsStore((state) => state.claudeRemainingPct);
  const fallbackThresholdPct = useSettingsStore((state) => state.fallbackThresholdPct);
  const setDispatchContext = useDispatchManager((state) => state.setContext);
  const isDispatching = useDispatchManager((state) => state.isDispatching);
  const readinessReport = useProjectManager((state) => state.readinessReport);
  const reconciliationConfidenceThreshold = useSettingsStore((state) => state.reconciliationConfidenceThreshold);
  const verifyProgress = useReconciliationManager((state) => state.verifyProgress);
  const verifyProgressAI = useReconciliationManager((state) => state.verifyProgressAI);
  const reconciliationFooterState = useReconciliationManager((state) => state.footerState);

  // Track dispatch completion to trigger data refresh
  const [refreshKey, setRefreshKey] = useState(0);
  const wasDispatchingRef = useRef(false);

  // Core state
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectData | null>(null);
  const [milestones, setMilestones] = useState<OverviewMilestoneData[]>([]);
  const [health, setHealth] = useState<HealthData[]>([]);
  const [qualityIssues, setQualityIssues] = useState<QualityIssue[]>([]);
  const [gates, setGates] = useState<GateData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dispatchMode, setDispatchMode] = useState("standard");
  const [changedFiles, setChangedFiles] = useState<string[]>([]);
  const [taskAdvice, setTaskAdvice] = useState<Record<string, DispatchAdvice>>({});
  const lastAdviceRequestKey = useRef<string | null>(null);

  // Progressive loading states (Phase 2)
  const [projectLoaded, setProjectLoaded] = useState(false);
  const [milestonesLoaded, setMilestonesLoaded] = useState(false);
  const [healthLoaded, setHealthLoaded] = useState(false);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);


  // Phase 6: Commit flow state
  const [showCommitPopover, setShowCommitPopover] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [isCommitting, setIsCommitting] = useState(false);
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);

  // Ask Input state
  const [askPrompt, setAskPrompt] = useState("");

  // Phase 4: Sessions for sidebar
  const [sessions, setSessions] = useState<RecentSession[]>([]);

  // Diff stats
  const [totalAdded, setTotalAdded] = useState(0);
  const [totalRemoved, setTotalRemoved] = useState(0);

  // Detect dispatch completion and trigger data refresh
  useEffect(() => {
    // When dispatch transitions from running to completed, refresh data
    // Small delay to allow auto-mark toggle to persist to ROADMAP.md first
    if (wasDispatchingRef.current && !isDispatching) {
      const timer = setTimeout(() => setRefreshKey((k) => k + 1), 600);
      return () => clearTimeout(timer);
    }
    wasDispatchingRef.current = isDispatching;
  }, [isDispatching]);

  // OPTIMIZED DATA FETCHING (Phases 1-3)
  useEffect(() => {
    const fetchData = async () => {
      if (!projectPath) {
        setProject(null);
        setMilestones([]);
        setHealth([]);
        setQualityIssues([]);
        setGates([]);
        setChangedFiles([]);
        setSessions([]);
        setLoading(false);
        setProjectLoaded(false);
        setMilestonesLoaded(false);
        setHealthLoaded(false);
        setSessionsLoaded(false);
        return;
      }
      if (!isBackendConnected()) {
        setLoading(false);
        return;
      }

      // Phase 2: Check cache first
      const cacheKey = `${projectPath}-${refreshKey}`;
      const cached = getCached<{
        project: ProjectData;
        milestones: OverviewMilestoneData[];
        health: HealthData[];
        qualityIssues: QualityIssue[];
        gates: GateData[];
        changedFiles: string[];
        sessions: RecentSession[];
        totalAdded: number;
        totalRemoved: number;
      }>(cacheKey);

      if (cached && refreshKey === 0) {
        // Use cached data immediately (only on initial load, not after dispatch)
        setProject(cached.project);
        setMilestones(cached.milestones);
        setHealth(cached.health);
        setQualityIssues(cached.qualityIssues);
        setGates(cached.gates);
        setChangedFiles(cached.changedFiles);
        setSessions(cached.sessions);
        setTotalAdded(cached.totalAdded);
        setTotalRemoved(cached.totalRemoved);
        setLoading(false);
        setProjectLoaded(true);
        setMilestonesLoaded(true);
        setHealthLoaded(true);
        setSessionsLoaded(true);
        return;
      }

      // Seed project data from projectManager to avoid full-page skeleton.
      // The picker already fetched this data — use it immediately.
      const currentProject = useProjectManager.getState().currentProject;
      const canSeed = currentProject && (currentProject.path === projectPath || currentProject.id === projectPath);

      if (canSeed) {
        const seededProject: ProjectData = {
          name: currentProject.name,
          summary:
            currentProject.readmeSummary ||
            "README summary unavailable. Add a top-level project description to README.",
          branch: currentProject.branch || "unknown",
          branchStrategy: deriveBranchStrategy(currentProject.branch || "unknown"),
          uncommitted: currentProject.uncommitted,
          lastSession: currentProject.lastSession || "N/A",
          costWeek: currentProject.costWeek || "N/A",
          totalSessions: currentProject.totalSessions,
        };
        setProject(seededProject);
        setProjectLoaded(true);
        setLoading(false);
      } else {
        setLoading(true);
        setProjectLoaded(false);
      }

      setError(null);
      setMilestonesLoaded(false);
      setHealthLoaded(false);
      setSessionsLoaded(false);

      const _t0 = performance.now();
      try {
        // Phase 2: Progressive rendering - fetch project data first (FAST)
        const projectData = await api.getProject(projectPath);
        const mappedProject: ProjectData = {
          name: projectData.name,
          summary:
            projectData.readmeSummary ||
            "README summary unavailable. Add a top-level project description to README.",
          branch: projectData.branch || "unknown",
          branchStrategy: deriveBranchStrategy(projectData.branch || "unknown"),
          uncommitted: projectData.uncommitted,
          lastSession: projectData.lastSession || "N/A",
          costWeek: projectData.costWeek || "N/A",
          totalSessions: projectData.totalSessions,
        };
        setProject(mappedProject);
        setProjectLoaded(true);
        setLoading(false); // Show project info immediately!

        // Phase 1: Fetch everything else in parallel (skip health - use readiness data instead)
        const [roadmapRes, gitRes, gatesRes, timelineRes] = await Promise.allSettled([
          api.getRoadmap(projectPath),
          api.getGitStatus(projectPath),
          api.getGateResults(projectPath),
          api.getTimeline(projectPath, 10),
        ]);

        // Local variables for cache (React setState is async, so state vars are stale at cache time)
        let cachedMilestones: OverviewMilestoneData[] = [];
        let cachedGates: GateData[] = [];
        let cachedChangedFiles: string[] = [];
        let cachedSessions: RecentSession[] = [];
        let cachedTotalAdded = 0;
        let cachedTotalRemoved = 0;

        // Handle roadmap
        if (roadmapRes.status === "fulfilled") {
          const mappedMilestones: OverviewMilestoneData[] = roadmapRes.value.milestones.map((m, i) => ({
            id: m.id || i + 1,
            title: m.title,
            phase: m.phase || `Milestone ${i + 1}`,
            sprint: m.sprint || `Phase ${m.id || i + 1}`,
            items: m.items.map((item) => ({
              text: item.text,
              done: item.done,
              prompt: item.prompt,
            })),
          }));
          setMilestones(mappedMilestones);
          cachedMilestones = mappedMilestones;
        } else {
          console.warn("Failed to fetch roadmap:", roadmapRes.reason);
          setMilestones([]);
        }
        setMilestonesLoaded(true);

        // Handle git status
        if (gitRes.status === "fulfilled") {
          const allChanges = [
            ...gitRes.value.uncommitted.map((f) => f.file),
            ...gitRes.value.untracked.map((f) => f.file),
          ];
          setChangedFiles(allChanges);
          cachedChangedFiles = allChanges;
        } else {
          console.warn("Failed to fetch git status:", gitRes.reason);
          setChangedFiles([]);
        }

        // Use readiness report for quality issues (faster, more complete than health endpoint)
        if (readinessReport?.checks) {
          // Helper to map readiness severity to health status
          const severityToStatus = (severity: string): Status => {
            if (severity === "critical") return "fail";
            if (severity === "important") return "warn";
            return "warn"; // nice_to_have
          };

          // Map readiness checks to health format for validation list
          const mappedHealth = readinessReport.checks.map((check) => ({
            name: check.name,
            status: check.passed ? ("pass" as Status) : severityToStatus(check.severity),
            detail: check.message,
          }));
          setHealth(mappedHealth);

          // Extract failed/warning checks as quality issues
          const newIssues = readinessReport.checks
            .filter((check) => !check.passed)
            .map((check) => ({
              severity: severityToStatus(check.severity),
              title: `${check.name}: ${check.message}`,
              suggestion: check.remediation ||
                         (check.severity === "critical"
                           ? "Address this immediately"
                           : "Review and resolve when possible"),
            }));
          setQualityIssues(newIssues);
        } else {
          // Fallback: no readiness data available
          setHealth([]);
          setQualityIssues([]);
        }
        setHealthLoaded(true);

        // Handle gates
        if (gatesRes.status === "fulfilled") {
          const mappedGates = gatesRes.value.gates.map((gate) => ({
            name: gate.name,
            status:
              gate.status === "pass" || gate.status === "warn" || gate.status === "fail"
                ? gate.status
                : "warn",
            detail: gate.message,
          }));
          setGates(mappedGates);
          cachedGates = mappedGates;
        } else {
          console.warn("Failed to fetch gate results:", gatesRes.reason);
          setGates([]);
        }

        // Handle timeline
        if (timelineRes.status === "fulfilled") {
          const recentSessions: RecentSession[] = timelineRes.value.entries.map((entry: TimelineEntry) => {
            // Clean summary: strip markdown headers, trim whitespace
            let cleanSummary = (entry.summary || "No summary")
              .replace(/^#+\s*/gm, "")   // Strip markdown headers
              .replace(/\*\*/g, "")        // Strip bold markers
              .replace(/\n.*/s, "")        // Take only first line
              .trim();
            if (cleanSummary.length > 80) {
              cleanSummary = cleanSummary.slice(0, 80) + "...";
            }

            // Format date: ISO -> short display
            let displayDate = entry.date;
            try {
              const d = new Date(entry.date);
              if (!isNaN(d.getTime())) {
                const now = Date.now();
                const diffMs = now - d.getTime();
                const diffH = Math.floor(diffMs / 3600000);
                if (diffH < 1) {
                  displayDate = `${Math.max(1, Math.floor(diffMs / 60000))}m ago`;
                } else if (diffH < 24) {
                  displayDate = `${diffH}h ago`;
                } else {
                  displayDate = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                }
              }
            } catch { /* keep raw date */ }

            return {
              id: entry.sessionId,
              summary: cleanSummary,
              date: displayDate,
              duration: `${entry.durationMinutes}m`,
              cost: entry.costEstimate ? `$${entry.costEstimate.toFixed(2)}` : undefined,
              linesAdded: 0,
              linesRemoved: 0,
              testsPassed: entry.testResults?.passed ?? true,
              provider: entry.provider || "claude",
            };
          });
          setSessions(recentSessions);
          cachedSessions = recentSessions;

          const added = recentSessions.reduce((sum, s) => sum + s.linesAdded, 0);
          const removed = recentSessions.reduce((sum, s) => sum + s.linesRemoved, 0);
          setTotalAdded(added);
          setTotalRemoved(removed);
          cachedTotalAdded = added;
          cachedTotalRemoved = removed;
        } else {
          console.error("Failed to fetch timeline:", timelineRes.reason);
          setSessions([]);
        }
        setSessionsLoaded(true);

        console.log(`%c[OverviewTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");

        // Phase 2: Cache the results (health/qualityIssues derived from readiness, not fetched)
        setCache(cacheKey, {
          project: mappedProject,
          milestones: cachedMilestones,
          health: health,
          qualityIssues: qualityIssues,
          gates: cachedGates,
          changedFiles: cachedChangedFiles,
          sessions: cachedSessions,
          totalAdded: cachedTotalAdded,
          totalRemoved: cachedTotalRemoved,
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to fetch project data");
        setLoading(false);
      }
    };

    void fetchData();
    // refreshKey changes when dispatch completes, invalidate cache
    if (refreshKey > 0) {
      invalidateCache(projectPath || '');
    }
  }, [projectPath, refreshKey]);

  const totalItems = milestones.reduce((s, m) => s + m.items.length, 0);
  const completedItems = milestones.reduce(
    (s, m) => s + m.items.filter((i) => i.done).length,
    0
  );
  const progress = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 100;
  const activeMilestone =
    milestones.find((m) => m.items.some((i) => !i.done)) ||
    milestones[milestones.length - 1];

  useEffect(() => {
    if (!projectPath || !isBackendConnected() || !activeMilestone) {
      setTaskAdvice({});
      lastAdviceRequestKey.current = null;
      return;
    }

    const pendingItems = activeMilestone.items.filter((item) => !item.done);
    if (pendingItems.length === 0) {
      setTaskAdvice({});
      lastAdviceRequestKey.current = null;
      return;
    }

    const adviceCandidates = pendingItems.slice(0, 6);
    const requestKey = JSON.stringify({
      projectPath,
      preferredFallback,
      usageMode,
      claudeRemainingPct,
      fallbackThresholdPct,
      tasks: adviceCandidates.map((item) => item.text),
    });
    if (lastAdviceRequestKey.current === requestKey) {
      return;
    }
    lastAdviceRequestKey.current = requestKey;

    // Check module-level cache first -- survives tab switches and remounts
    const cacheKey = `advice:${requestKey}`;
    const cached = getCached<Record<string, DispatchAdvice>>(cacheKey);
    if (cached) {
      setTaskAdvice(cached);
      return;
    }

    let cancelled = false;
    const fetchAdvice = async () => {
      const entries = await Promise.all(
        adviceCandidates.map(async (item) => {
          const prompt = item.prompt || `Implement: ${item.text.replace(/^\*\*[\d.]+\*\*\s*/, "")}`;
          try {
            const advice = await api.dispatchAdvice({
              prompt,
              projectPath,
              preferredFallback,
              usageMode,
              claudeRemainingPct,
              fallbackThresholdPct,
            });
            return [item.text, advice] as const;
          } catch {
            return null;
          }
        })
      );
      if (cancelled) return;

      const nextAdvice: Record<string, DispatchAdvice> = {};
      for (const entry of entries) {
        if (!entry) continue;
        const [taskText, advice] = entry;
        nextAdvice[taskText] = advice;
      }
      setTaskAdvice(nextAdvice);
      setCache(cacheKey, nextAdvice);
    };

    void fetchAdvice();
    return () => {
      cancelled = true;
    };
  }, [activeMilestone, preferredFallback, projectPath, usageMode, claudeRemainingPct, fallbackThresholdPct]);

  const handleStartSession = async (prompt?: string, itemRef?: { text: string; prompt?: string }) => {
    let finalPrompt = prompt || "Continue work on the current task";

    const source: DispatchContext["source"] = itemRef ? "task" : "overview";
    setDispatchContext({ prompt: finalPrompt, mode: dispatchMode, source, itemRef });
    if (onShowPreFlight) {
      onShowPreFlight(finalPrompt, dispatchMode, source, itemRef);
    } else {
      onStart?.(finalPrompt, dispatchMode);
    }
  };

  const handleFixIssue = (issue: QualityIssue) => {
    const fixPrompt = `Fix the following quality issue:\n\nIssue: ${issue.title}\nSuggestion: ${issue.suggestion}`;
    setDispatchContext({ prompt: fixPrompt, mode: dispatchMode, source: "fix" });
    if (onShowPreFlight) {
      onShowPreFlight(fixPrompt, dispatchMode, "fix");
    } else {
      onStart?.(fixPrompt, dispatchMode);
    }
  };

  const handleToggleDone = (item: OverviewMilestoneItem) => {
    // Optimistic local update
    setMilestones((prev) =>
      prev.map((m) => ({
        ...m,
        items: m.items.map((i) => (i.text === item.text ? { ...i, done: !i.done } : i)),
      }))
    );
    // Persist to backend (writes to ROADMAP.md)
    if (projectPath) {
      api.toggleRoadmapItem(projectPath, item.text).catch((err) => {
        console.warn("Failed to persist toggle:", err);
        // Revert on failure
        setMilestones((prev) =>
          prev.map((m) => ({
            ...m,
            items: m.items.map((i) => (i.text === item.text ? { ...i, done: item.done } : i)),
          }))
        );
      });
    }
  };

  // Phase 2: Open Terminal handler
  const handleOpenTerminal = () => {
    // Empty prompt = interactive terminal mode
    setDispatchContext({ prompt: "", mode: dispatchMode, source: "overview" });
    if (onShowPreFlight) {
      onShowPreFlight("", dispatchMode, "overview");
    }
  };

  // Ask Input dispatch handler -- trigger pre-flight flow
  const handleAskDispatch = () => {
    if (!askPrompt.trim()) return;
    setDispatchContext({ prompt: askPrompt.trim(), mode: dispatchMode, source: "ask" });
    if (onShowPreFlight) {
      onShowPreFlight(askPrompt.trim(), dispatchMode, "ask");
    }
  };

  // Phase 6: Commit flow
  const handleOpenCommit = async () => {
    if (!projectPath || changedFiles.length === 0) {
      toast.info("No Changes", "Working tree is clean, nothing to commit.");
      return;
    }

    try {
      const lightModel = useSettingsStore.getState().lightModel;
      const generated = await api.generateCommitMessageAI(projectPath, lightModel);
      setCommitMessage(generated.message);
      setShowCommitPopover(true);
      if (generated.ai_generated) {
        toast.success("AI Generated", generated.summary || "Commit message generated by Claude");
      } else if (generated.error) {
        toast.warning("Using Heuristic", `${generated.error}. Generated basic message instead.`);
      }
    } catch (e) {
      console.warn("AI commit message failed, falling back to heuristic:", e);
      try {
        const fallback = await api.generateCommitMessage(projectPath);
        setCommitMessage(fallback.message);
      } catch {
        setCommitMessage("");
      }
      setShowCommitPopover(true);
    }
  };

  const handleCommit = async () => {
    if (!projectPath || !commitMessage.trim()) return;

    setIsCommitting(true);
    try {
      // Stage all and commit
      await api.stageAll(projectPath);
      const result = await api.commitStaged(projectPath, commitMessage.trim());
      if (result.success) {
        toast.success("Committed", `Changes committed: ${result.hash?.slice(0, 7) || "done"}`);
        setShowCommitPopover(false);
        setCommitMessage("");
        // Refresh git status
        const gitStatus = await api.getGitStatus(projectPath);
        const allChanges = [
          ...gitStatus.uncommitted.map((f) => f.file),
          ...gitStatus.untracked.map((f) => f.file),
        ];
        setChangedFiles(allChanges);
        // Update project uncommitted count
        setProject((prev) =>
          prev ? { ...prev, uncommitted: allChanges.length } : prev
        );
      } else {
        toast.error("Commit Failed", result.message);
      }
    } catch (e) {
      toast.error("Commit Error", e instanceof Error ? e.message : "Failed to commit");
    } finally {
      setIsCommitting(false);
    }
  };

  // Phase 9: Session report click
  const handleSessionClick = (sessionId: string) => {
    onReport?.(sessionId);
  };

  // Phase 2: Progressive loading - show skeleton for initial load only
  if (loading && !projectLoaded) {
    return (
      <div className="flex flex-col gap-3.5 p-5">
        <SkeletonCard />
        <SkeletonCard />
        <div className="grid grid-cols-[1fr_340px] gap-3.5">
          <SkeletonMilestone />
          <SkeletonSession />
        </div>
      </div>
    );
  }

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view overview data.
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-mc-red p-10 text-center">
        {error}
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        No project data available.
      </div>
    );
  }

  const needsFooterPadding = reconciliationFooterState !== "hidden";

  return (
    <div className={`flex flex-col gap-3.5 animate-fade-in ${needsFooterPadding ? "pb-12" : ""}`}>
      {/* ============================================ */}
      {/* ACTION STRIP -- flat, no card background */}
      {/* ============================================ */}
      <div className="flex items-center gap-2 py-1.5">
        <Button small onClick={handleOpenTerminal}>
          <Icons.play size={10} /> Open Terminal
        </Button>
        <div className="w-px h-5 bg-mc-border-1" />
        <Button small onClick={handleOpenCommit}>
          Commit
        </Button>

        <div className="flex-1" />

        {/* Diff stats */}
        <span className="text-[11px] font-mono text-mc-green font-semibold">+{totalAdded.toLocaleString()}</span>
        <span className="text-[11px] font-mono text-mc-red font-semibold">-{totalRemoved.toLocaleString()}</span>
        <div className="w-px h-3.5 bg-mc-border-1 mx-0.5" />
        <span className="text-[10px] font-mono text-mc-text-3">
          {project.totalSessions} sessions
        </span>
        <div className="w-px h-3.5 bg-mc-border-1 mx-0.5" />
        <span className="text-[10px] font-mono text-mc-text-3">
          {project.costWeek}/wk
        </span>
        <div className="w-px h-5 bg-mc-border-1 mx-0.5" />

        {/* Last report link */}
        <button
          onClick={() => onReport?.(sessions[0]?.id)}
          className="text-[11px] font-medium font-mono text-mc-accent bg-transparent border-none cursor-pointer p-0"
        >
          Last report {"\u2192"}
        </button>
      </div>

      {/* ============================================ */}
      {/* PROGRESS HERO -- ring + name + README merged */}
      {/* ============================================ */}
      <div className="px-5 py-4 rounded-xl bg-mc-surface-1 border border-mc-border-0">
        <div className="flex items-center gap-[18px]">
          {/* 48px progress ring */}
          <div className="relative w-12 h-12 shrink-0">
            <svg width="48" height="48" viewBox="0 0 48 48" className="-rotate-90">
              <circle cx="24" cy="24" r="20" fill="none" stroke={t.surface3} strokeWidth="3.5" />
              <circle
                cx="24"
                cy="24"
                r="20"
                fill="none"
                stroke={progress >= 80 ? t.green : t.accent}
                strokeWidth="3.5"
                strokeDasharray={2 * Math.PI * 20}
                strokeDashoffset={(2 * Math.PI * 20) * (1 - progress / 100)}
                strokeLinecap="round"
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-sm font-extrabold font-mono text-mc-text-0">
              {progress}%
            </span>
          </div>

          {/* Name + item count on same baseline, README + progress bar below */}
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-base font-extrabold text-mc-text-0 tracking-tight">
                {project.name}
              </span>
              <span className="text-[11px] font-mono text-mc-text-3">
                {completedItems}/{totalItems} items {"\u00B7"} {milestones.length} milestones
              </span>
            </div>
            {/* README 2-line clamp */}
            <div className="text-[11.5px] text-mc-text-3 leading-normal mt-1 overflow-hidden text-ellipsis line-clamp-2">
              {project.summary}
            </div>
            {/* Progress bar -- inline with text column */}
            <div className="mt-2 h-1 rounded-sm bg-mc-surface-3 overflow-hidden">
              <div
                className="h-full rounded-sm transition-[width] duration-500 ease-in-out"
                style={{
                  width: `${progress}%`,
                  background: `linear-gradient(90deg, ${t.accent}, ${t.accentDark})`,
                }}
              />
            </div>
          </div>
        </div>

        {/* AI Verify buttons -- below hero, only after milestones loaded */}
        {milestonesLoaded && totalItems > 0 && progress < 100 && (
          <div className="mt-2.5 flex gap-1.5 items-center">
            <Button
              small
              primary
              onClick={() => projectPath && verifyProgressAI(projectPath, { confidenceThreshold: reconciliationConfidenceThreshold })}
              disabled={reconciliationFooterState === "analyzing"}
            >
              {reconciliationFooterState === "analyzing" ? "AI Analyzing..." : "AI Verify Progress"}
            </Button>
            <Button
              small
              onClick={() => projectPath && verifyProgress(projectPath, { confidenceThreshold: reconciliationConfidenceThreshold })}
              disabled={reconciliationFooterState === "analyzing"}
            >
              Verify Progress
            </Button>
            <span className="text-[10px] text-mc-text-3 italic">
              (AI uses Claude Code to read your code)
            </span>
          </div>
        )}
      </div>

      {/* ============================================ */}
      {/* BRANCH BAR + QUEUE ROW */}
      {/* ============================================ */}
      <div className="rounded-lg overflow-hidden bg-mc-surface-0 border border-mc-border-0">
        {/* Row 1: Branch info + dispatch mode */}
        <div className="flex items-center gap-3 px-4 py-[9px] border-b border-mc-border-0">
          <span className="text-mc-text-3">
            <Icons.branch size={12} />
          </span>
          <span className="text-[11.5px] font-mono font-semibold text-mc-text-1">
            {project.branch}
          </span>
          <Tag
            color={project.branchStrategy === "trunk-based" ? t.cyan : project.branchStrategy === "git-flow" ? t.amber : t.accent}
            bg={project.branchStrategy === "trunk-based" ? t.cyanMuted : project.branchStrategy === "git-flow" ? t.amberMuted : t.accentMuted}
          >
            {project.branchStrategy}
          </Tag>
          <div className="w-px h-3.5 bg-mc-border-1" />
          {project.uncommitted > 0 ? (
            <Tag color={t.amber} bg={t.amberMuted}>
              {project.uncommitted} uncommitted
            </Tag>
          ) : (
            <Tag color={t.green} bg={t.greenMuted}>
              Clean
            </Tag>
          )}
          <div className="flex-1" />
          <Select
            value={dispatchMode}
            onChange={setDispatchMode}
            small
            options={[
              { value: "standard", label: "Standard" },
              { value: "with-review", label: "With Review (--agents)" },
              { value: "full-pipeline", label: "Full Pipeline" },
              { value: "blitz", label: "Blitz Mode", icon: <span className="text-[#fbbf24]">{"\u26A1"}</span> },
            ]}
          />
          <Button small onClick={onNavigateToSettings}>Agents</Button>
        </div>

        {/* Row 2: Changed Files OR Clean */}
        {changedFiles.length > 0 ? (
          <div className="flex items-center gap-2.5 px-4 py-2">
            <Tag color={t.amber}>{changedFiles.length} changes</Tag>
            <div className="text-[11px] text-mc-text-2 flex-1 min-w-0">
              <span className="whitespace-nowrap overflow-hidden text-ellipsis block">
                {changedFiles.slice(0, 3).join(", ")}
                {changedFiles.length > 3 ? ` +${changedFiles.length - 3} more` : ""}
              </span>
            </div>
            <Button small onClick={onNavigateToGit}>
              Go to Git {"\u2192"}
            </Button>
          </div>
        ) : (
          <div className="px-4 py-2.5 text-[11px] text-mc-text-3 flex items-center gap-2">
            <Tag color={t.green} bg={t.greenMuted}>Clean</Tag>
            <span>Working tree clean</span>
          </div>
        )}
      </div>

      {/* ============================================ */}
      {/* ASK INPUT -- persistent prompt bar */}
      {/* ============================================ */}
      <AskInput
        askPrompt={askPrompt}
        onAskPromptChange={setAskPrompt}
        dispatchMode={dispatchMode}
        onDispatch={handleAskDispatch}
      />

      {/* ============================================ */}
      {/* LIVE FEED */}
      {/* ============================================ */}
      {projectPath && (
        <LiveFeed
          projectPath={projectPath}
          onReport={onReport}
          onDispatchFromQueue={(item) => {
            setDispatchContext({
              prompt: item.prompt,
              mode: item.mode,
              source: item.source as DispatchContext["source"],
              itemRef: item.itemRef,
            });
            onShowPreFlight?.(item.prompt, item.mode, item.source as DispatchContext["source"], item.itemRef);
          }}
        />
      )}

      {/* ============================================ */}
      {/* MAIN CONTENT + SIDEBAR */}
      {/* ============================================ */}
      <div className="grid grid-cols-[1fr_340px] gap-3.5 items-start">
        {/* LEFT COLUMN: Milestone + Quality Issues */}
        <div className="flex flex-col gap-3.5">
          <Section>
            {!milestonesLoaded ? (
              <SkeletonMilestone />
            ) : activeMilestone ? (
              <MilestoneCard
                milestone={activeMilestone}
                expandedItem={expandedItem}
                onExpandItem={setExpandedItem}
                projectPath={projectPath}
                usageMode={usageMode}
                taskAdvice={taskAdvice}
                onStartSession={(item) => {
                  const prompt = item.prompt || `Implement: ${item.text.replace(/^\*\*[\d.]+\*\*\s*/, "")}`;
                  handleStartSession(prompt, { text: item.text, prompt: item.prompt });
                }}
                onToggleDone={handleToggleDone}
                onRetryWithContext={(item, retryPrompt) => handleStartSession(retryPrompt, { text: item.text, prompt: item.prompt })}
                onEditPrompt={(item, newPrompt) => {
                  setMilestones((prev) =>
                    prev.map((m) => ({
                      ...m,
                      items: m.items.map((i) =>
                        i.text === item.text ? { ...i, prompt: newPrompt } : i
                      ),
                    }))
                  );
                }}
              />
            ) : (
              <div className="p-3.5 text-mc-text-3 text-xs">
                No roadmap milestones available.
              </div>
            )}
          </Section>

          {/* Quality Issues section */}
          {qualityIssues.length > 0 && (
          <Section label={`Quality Issues \u00B7 ${qualityIssues.length}`} right="last gate run">
            <div className="py-1">
              {!healthLoaded ? (
                <SkeletonText lines={3} />
              ) : (
                  qualityIssues.map((issue, i) => (
                    <div
                      key={i}
                      className={`flex items-start gap-2.5 px-3.5 py-2.5 ${
                        i < qualityIssues.length - 1 ? "border-b border-mc-border-0" : ""
                      } ${issue.severity === "fail" ? "bg-mc-red-muted" : ""}`}
                    >
                      {/* Icon column */}
                      <div className="pt-0.5 shrink-0">
                        {issue.severity === "fail"
                          ? <span className="text-mc-red"><Icons.x size={10} /></span>
                          : <span className="text-mc-amber"><Icons.alert size={12} /></span>
                        }
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-1.5 mb-[3px]">
                          <SeverityTag status={issue.severity} />
                          <span className={`text-xs font-semibold ${issue.severity === "fail" ? "text-mc-red" : "text-mc-text-1"}`}><InlineMarkdown>{issue.title}</InlineMarkdown></span>
                        </div>
                        <div className="text-[10.5px] text-mc-text-3 leading-[1.4]"><InlineMarkdown>{issue.suggestion}</InlineMarkdown></div>
                      </div>
                      <Button
                        small
                        primary={issue.severity === "fail"}
                        danger={issue.severity === "fail"}
                        onClick={() => handleFixIssue(issue)}
                      >
                        Fix
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </Section>
          )}
        </div>

        {/* RIGHT COLUMN: Recent Sessions + Validation */}
        <div className="flex flex-col gap-3.5">
          {/* Recent Sessions section */}
          <Section label="Recent Sessions">
            {!sessionsLoaded ? (
              <SkeletonSession />
            ) : (
              <RecentSessions sessions={sessions} onSessionClick={handleSessionClick} />
            )}
          </Section>

          <Section label="Validation" right={
            <button
              onClick={() => useProjectManager.getState().setScreen("scorecard")}
              className="bg-transparent border-none text-mc-accent text-[10px] font-mono cursor-pointer flex items-center gap-1 hover:underline"
            >
              {Icons.bolt({ size: 9, color: t.accent })} Scan Readiness
            </button>
          }>
            <ValidationList health={health} gates={gates} />
          </Section>
        </div>
      </div>

      {/* ============================================ */}
      {/* FOOTER BAR */}
      {/* ============================================ */}
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-mc-surface-0 border border-mc-border-0 text-[10px] font-mono text-mc-text-3">
        <div className="flex items-center gap-1.5">
          <Icons.branch size={10} />
          <span className="text-mc-text-2">{project.branch}</span>
        </div>

        <div className="w-px h-3 bg-mc-border-1" />

        <span>
          {changedFiles.length > 0 ? `${changedFiles.length} modified` : "Clean tree"}
        </span>

        <div className="w-px h-3 bg-mc-border-1" />

        <span>
          Provider: <span className="text-mc-accent">{sessions[0]?.provider ? sessions[0].provider.charAt(0).toUpperCase() + sessions[0].provider.slice(1) : "Claude"}</span>
        </span>

        <div className="flex-1" />

        <span>{project.totalSessions} sessions</span>

        <div className="w-px h-3 bg-mc-border-1" />

        <span>Last: {project.lastSession}</span>
      </div>

      {/* ============================================ */}
      {/* COMMIT POPOVER */}
      {/* ============================================ */}
      {showCommitPopover && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-[1000]"
          onClick={() => setShowCommitPopover(false)}
        >
          <div
            className="bg-mc-surface-1 border border-mc-border-1 rounded-xl p-5 w-[450px] max-w-[90vw]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-sm font-bold text-mc-text-0 mb-3">
              Commit Changes
            </div>
            <div className="text-[11px] text-mc-text-3 mb-2.5 flex items-center justify-between">
              <span>{changedFiles.length} file{changedFiles.length !== 1 ? "s" : ""} to commit</span>
              <button
                disabled={isGeneratingAI}
                onClick={async (e) => {
                  e.preventDefault();
                  setIsGeneratingAI(true);
                  try {
                    const lm = useSettingsStore.getState().lightModel;
                    const result = await api.generateCommitMessageAI(projectPath!, lm);
                    setCommitMessage(result.message);
                    if (result.ai_generated) {
                      toast.success("AI Generated", result.summary || "Message generated by Claude");
                    } else {
                      toast.warning("Heuristic", result.error || "AI generation failed");
                    }
                  } catch {
                    toast.warning("Failed", "Could not generate AI commit message");
                  } finally {
                    setIsGeneratingAI(false);
                  }
                }}
                className={`border-none text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  isGeneratingAI
                    ? "bg-mc-surface-2 text-mc-accent cursor-default"
                    : "bg-transparent text-mc-accent cursor-pointer hover:bg-mc-surface-2"
                }`}
              >
                {isGeneratingAI ? "Generating ✨" : "⚡ Regenerate with AI"}
              </button>
            </div>
            <textarea
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              placeholder="Commit message..."
              className="w-full h-[100px] bg-mc-surface-2 border border-mc-border-1 rounded-lg p-3 text-xs text-mc-text-1 font-mono resize-y outline-none"
              autoFocus
            />
            <div className="flex gap-2 mt-3 justify-end">
              <Button onClick={() => setShowCommitPopover(false)}>Cancel</Button>
              <Button primary onClick={handleCommit} disabled={!commitMessage.trim() || isCommitting}>
                {isCommitting ? "Committing..." : "Commit"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
