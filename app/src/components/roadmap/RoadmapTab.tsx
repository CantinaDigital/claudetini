import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "../../styles/tokens";
import { Icons } from "../ui/Icons";
import { Tag } from "../ui/Tag";
import { Button } from "../ui/Button";
import { useDispatchManager } from "../../managers/dispatchManager";
import { useParallelManager } from "../../managers/parallelManager";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { api, isBackendConnected } from "../../api/backend";
import type { Milestone, MilestoneItem } from "../../types";

/** Extract display title from task text. Splits on em-dash separator if present. */
function displayTitle(text: string): string {
  const idx = text.indexOf(" \u2014 ");
  if (idx > 0 && idx < 120) return text.substring(0, idx);
  return text;
}

interface PhaseGroup {
  label: string;
  milestones: Milestone[];
}

interface RoadmapTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  onStartSession?: (item: MilestoneItem) => void;
  onStartMilestone?: (milestone: Milestone) => void;
  onRunParallel?: (milestone: Milestone) => void;
  onToggleDone?: (item: MilestoneItem) => void;
  onEditPrompt?: (item: MilestoneItem, newPrompt: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}

export function RoadmapTab({
  projectPath,
  isActive = true,
  onStartSession,
  onStartMilestone,
  onRunParallel,
  onToggleDone,
  onEditPrompt,
  onShowConfirm,
}: RoadmapTabProps) {
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [editText, setEditText] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [focusedMilestoneIdx, setFocusedMilestoneIdx] = useState(-1);
  const milestoneRefs = useRef<(HTMLDivElement | null)[]>([]);
  const hasLoaded = useRef(false);

  // Refresh after dispatch completes (same pattern as OverviewTab)
  const [refreshKey, setRefreshKey] = useState(0);
  const isDispatching = useDispatchManager((s) => s.isDispatching);
  const wasDispatchingRef = useRef(false);

  useEffect(() => {
    if (wasDispatchingRef.current && !isDispatching) {
      // Delay to let auto-mark/batch-toggle persist to ROADMAP.md first
      const timer = setTimeout(() => setRefreshKey((k) => k + 1), 800);
      return () => clearTimeout(timer);
    }
    wasDispatchingRef.current = isDispatching;
  }, [isDispatching]);

  // Refresh after parallel execution completes (backend marks items in ROADMAP.md during finalize)
  const parallelPhase = useParallelManager((s) => s.phase);
  const prevParallelPhaseRef = useRef(parallelPhase);

  useEffect(() => {
    const prev = prevParallelPhaseRef.current;
    prevParallelPhaseRef.current = parallelPhase;

    const wasActive = prev === "executing" || prev === "merging" || prev === "verifying" || prev === "finalizing";
    const isNowTerminal = parallelPhase === "complete" || parallelPhase === "failed";

    if (wasActive && isNowTerminal) {
      const timer = setTimeout(() => setRefreshKey((k) => k + 1), 500);
      return () => clearTimeout(timer);
    }
  }, [parallelPhase]);

  const { totalItems, completedItems, progress } = useMemo(() => {
    const total = milestones.reduce((s, m) => s + m.items.length, 0);
    const completed = milestones.reduce((s, m) => s + m.items.filter((i) => i.done).length, 0);
    return {
      totalItems: total,
      completedItems: completed,
      progress: total > 0 ? Math.round((completed / total) * 100) : 0,
    };
  }, [milestones]);

  const activeId = useMemo(() => {
    const activeMilestone = milestones.find((m) => m.items.some((i) => !i.done));
    return activeMilestone?.id ?? -1;
  }, [milestones]);

  const phases = useMemo<PhaseGroup[]>(() => {
    const groups: PhaseGroup[] = [];
    let lastPhase: string | null = null;

    milestones.forEach((m) => {
      const phase = m.phase || "Ungrouped";
      if (phase !== lastPhase) {
        groups.push({ label: phase, milestones: [] });
        lastPhase = phase;
      }
      groups[groups.length - 1].milestones.push(m);
    });

    return groups;
  }, [milestones]);

  const getPhaseStats = (ms: Milestone[]) => {
    const total = ms.reduce((s, m) => s + m.items.length, 0);
    const done = ms.reduce((s, m) => s + m.items.filter((i) => i.done).length, 0);
    return {
      total,
      done,
      pct: total > 0 ? Math.round((done / total) * 100) : 0,
      complete: done === total,
    };
  };

  const toggleMilestone = useCallback((id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const flatMilestones = useMemo(() => phases.flatMap((p) => p.milestones), [phases]);

  const handleMilestoneKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (flatMilestones.length === 0) return;
      let next = focusedMilestoneIdx;

      if (event.key === "ArrowDown") {
        next = Math.min(focusedMilestoneIdx + 1, flatMilestones.length - 1);
      } else if (event.key === "ArrowUp") {
        next = Math.max(focusedMilestoneIdx - 1, 0);
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (focusedMilestoneIdx >= 0) {
          toggleMilestone(flatMilestones[focusedMilestoneIdx].id);
        }
        return;
      } else if (event.key === "ArrowRight" && focusedMilestoneIdx >= 0) {
        event.preventDefault();
        const m = flatMilestones[focusedMilestoneIdx];
        if (!expanded.has(m.id)) toggleMilestone(m.id);
        return;
      } else if (event.key === "ArrowLeft" && focusedMilestoneIdx >= 0) {
        event.preventDefault();
        const m = flatMilestones[focusedMilestoneIdx];
        if (expanded.has(m.id)) toggleMilestone(m.id);
        return;
      } else {
        return;
      }
      event.preventDefault();
      setFocusedMilestoneIdx(next);
      milestoneRefs.current[next]?.focus();
    },
    [focusedMilestoneIdx, flatMilestones, expanded, toggleMilestone],
  );

  // Reset hasLoaded on project change so data is re-fetched
  useEffect(() => { hasLoaded.current = false; }, [projectPath]);

  useEffect(() => {
    // Defer initial fetch until tab becomes active (lazy loading)
    // Allow refreshKey > 0 through even when not active (dispatch/parallel completion refresh)
    if (!isActive && !hasLoaded.current && refreshKey === 0) return;

    const fetchData = async () => {
      if (!projectPath || !isBackendConnected()) {
        setMilestones([]);
        setExpanded(new Set());
        setLoading(false);
        return;
      }

      // On refresh (not initial load), don't show loading spinner — just silently update
      if (!hasLoaded.current) setLoading(true);
      hasLoaded.current = true;
      const _t0 = performance.now();
      try {
        const roadmap = await api.getRoadmap(projectPath);
        const mappedMilestones: Milestone[] = roadmap.milestones.map((m, i) => ({
          id: m.id || i + 1,
          phase: m.phase || `Milestone ${m.id || i + 1}`,
          title: m.title,
          sprint: m.sprint || `Phase ${m.id || i + 1}`,
          items: m.items.map((item) => ({
            text: item.text,
            done: item.done,
            prompt: item.prompt,
            context: item.context,
          })),
        }));
        setMilestones(mappedMilestones);

        // Only auto-expand on initial load, preserve user's expanded state on refresh
        if (refreshKey === 0) {
          const active = mappedMilestones.find((m) => m.items.some((i) => !i.done));
          setExpanded(active ? new Set([active.id]) : new Set());
        }
        console.log(`%c[RoadmapTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
      } catch (e) {
        console.warn("Failed to fetch roadmap:", e);
        if (!hasLoaded.current) setMilestones([]);
      } finally {
        setLoading(false);
      }
    };

    void fetchData();
  }, [projectPath, refreshKey, isActive]);

  const toggleItem = (itemText: string) => {
    setExpandedItem((prev) => (prev === itemText ? null : itemText));
  };

  const handleToggleDone = (item: MilestoneItem) => {
    const doToggle = () => {
      onToggleDone?.(item);
      setMilestones((prev) =>
        prev.map((m) => ({
          ...m,
          items: m.items.map((i) => (i.text === item.text ? { ...i, done: !i.done } : i)),
        }))
      );
    };

    if (!item.done && onShowConfirm) {
      onShowConfirm({
        title: "Mark as Complete",
        message: "Mark this item as complete without running a session?",
        confirmLabel: "Mark Complete",
        onConfirm: doToggle,
      });
    } else {
      doToggle();
    }
  };

  const handleStartEdit = (item: MilestoneItem) => {
    setEditingItem(item.text);
    setEditText(item.prompt || `Complete the following task: ${item.text}`);
  };

  const handleSaveEdit = (item: MilestoneItem) => {
    if (editText.trim()) {
      onEditPrompt?.(item, editText.trim());
    }
    setMilestones((prev) =>
      prev.map((m) => ({
        ...m,
        items: m.items.map((i) => (i.text === item.text ? { ...i, prompt: editText.trim() } : i)),
      }))
    );
    setEditingItem(null);
    setEditText("");
  };

  const handleSkip = (item: MilestoneItem) => {
    const doSkip = () => {
      setMilestones((prev) =>
        prev.map((m) => ({
          ...m,
          items: m.items.map((i) => (i.text === item.text ? { ...i, done: true } : i)),
        }))
      );
      setExpandedItem(null);
    };

    if (onShowConfirm) {
      onShowConfirm({
        title: "Skip Item",
        message: `Skip "${displayTitle(item.text)}"? This will mark it as complete without running a session.`,
        confirmLabel: "Skip",
        onConfirm: doSkip,
      });
    } else {
      doSkip();
    }
  };

  if (loading) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Loading roadmap...
      </div>
    );
  }

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view roadmap data.
      </div>
    );
  }

  if (milestones.length === 0) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        No roadmap data found for this project.
      </div>
    );
  }

  return (
    <div className="w-full animate-fade-in">
      {/* Global progress bar */}
      <div className="flex items-center gap-3.5 mb-6">
        <div className="flex-1 h-1.5 bg-mc-surface-2 rounded-sm overflow-hidden">
          <div
            className="h-full rounded-sm bg-gradient-to-r from-mc-green to-mc-green-light"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-sm font-bold text-mc-green font-mono">{progress}%</span>
        <span className="text-xs text-mc-text-3 font-mono">
          {completedItems}/{totalItems}
        </span>
      </div>

      <div className="flex flex-col gap-6">
        {(() => { let flatIdx = 0; return phases.map((phase, pi) => {
          const ps = getPhaseStats(phase.milestones);
          const hasActive = phase.milestones.some((m) => m.id === activeId);
          const allComplete = ps.complete;

          return (
            <div key={pi}>
              {/* Phase header */}
              <div className="flex items-center gap-2.5 mb-2.5 px-0.5">
                <span
                  className={`text-[10px] font-bold font-mono uppercase tracking-[0.08em] ${
                    hasActive ? "text-mc-accent" : allComplete ? "text-mc-green" : "text-mc-text-3"
                  }`}
                >
                  {phase.label}
                </span>
                <div className="flex-1 h-px bg-mc-border-0" />
                <div className="flex items-center gap-2">
                  <div className="w-[60px] h-[3px] bg-mc-surface-2 rounded-sm overflow-hidden">
                    <div
                      className={`h-full rounded-sm ${
                        allComplete ? "bg-mc-green" : hasActive ? "bg-mc-accent" : "bg-mc-text-3"
                      }`}
                      style={{ width: `${ps.pct}%` }}
                    />
                  </div>
                  <span
                    className={`text-[10px] font-mono font-semibold ${
                      allComplete ? "text-mc-green" : "text-mc-text-3"
                    }`}
                  >
                    {ps.done}/{ps.total}
                  </span>
                </div>
              </div>

              {/* Milestone cards */}
              <div className="flex flex-col gap-1">
                {phase.milestones.map((m) => {
                  const mDone = m.items.filter((i) => i.done).length;
                  const mTotal = m.items.length;
                  const complete = mDone === mTotal;
                  const isActive = m.id === activeId;
                  const isOpen = expanded.has(m.id);
                  const remaining = m.items.filter((i) => !i.done);
                  const mi = flatIdx++;
                  const isFocused = focusedMilestoneIdx === mi;

                  return (
                    <div
                      key={m.id}
                      ref={(el) => { milestoneRefs.current[mi] = el; }}
                      tabIndex={isFocused ? 0 : mi === 0 && focusedMilestoneIdx === -1 ? 0 : -1}
                      onFocus={() => setFocusedMilestoneIdx(mi)}
                      onKeyDown={handleMilestoneKeyDown}
                      className={`rounded-[10px] overflow-hidden outline-none border ${
                        isFocused
                          ? "border-mc-accent"
                          : isActive
                            ? "border-mc-accent-border bg-mc-surface-1"
                            : complete
                              ? "border-mc-border-0 bg-transparent"
                              : "border-mc-border-0 bg-mc-surface-0"
                      } ${isActive && !isFocused ? "bg-mc-surface-1" : ""}`}
                    >
                      {/* Milestone header */}
                      <div
                        onClick={() => toggleMilestone(m.id)}
                        className={`flex items-center gap-2.5 px-3.5 cursor-pointer select-none ${
                          isActive ? "py-3" : "py-[9px]"
                        }`}
                      >
                        {/* Numbered/check badge */}
                        {complete ? (
                          <div className="w-6 h-6 rounded-[7px] shrink-0 flex items-center justify-center text-[11px] font-bold font-mono bg-mc-green-muted border border-mc-green-border text-mc-green">
                            <Icons.check size={10} color={t.green} />
                          </div>
                        ) : isActive ? (
                          <div
                            className="w-6 h-6 rounded-[7px] shrink-0 flex items-center justify-center text-[11px] font-bold font-mono text-white"
                            style={{ background: `linear-gradient(135deg, ${t.accent}, ${t.accentDark})` }}
                          >
                            {m.id}
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-[7px] shrink-0 flex items-center justify-center text-[11px] font-bold font-mono bg-mc-surface-2 border border-mc-border-1 text-mc-text-3">
                            {m.id}
                          </div>
                        )}

                        {/* Title + subtitle */}
                        <div className="flex-1 min-w-0">
                          <div
                            className={`text-[13px] ${
                              isActive ? "font-semibold text-mc-text-0" : complete ? "font-medium text-mc-text-2" : "font-medium text-mc-text-1"
                            }`}
                          >
                            <InlineMarkdown>{m.title}</InlineMarkdown>
                          </div>
                          {isActive && remaining.length > 0 && (
                            <div className="text-[10px] font-mono text-mc-text-3 mt-px">
                              {remaining.length} remaining · up next: {displayTitle(remaining[0].text).substring(0, 40)}...
                            </div>
                          )}
                          {complete && !isOpen && (
                            <div className="text-[10px] font-mono text-mc-text-3 mt-px">
                              All {mTotal} items complete
                            </div>
                          )}
                        </div>

                        {/* Run All + Dot bar + count + chevron */}
                        <div className="flex items-center gap-2 shrink-0">
                          {remaining.length >= 2 && onRunParallel && (
                            <Button
                              small
                              onClick={(e) => {
                                e.stopPropagation();
                                onRunParallel(m);
                              }}
                            >
                              Parallel ({remaining.length})
                            </Button>
                          )}
                          {remaining.length > 0 && onStartMilestone && (
                            <Button
                              small
                              onClick={(e) => {
                                e.stopPropagation();
                                onStartMilestone(m);
                              }}
                            >
                              <Icons.play size={9} /> Run All ({remaining.length})
                            </Button>
                          )}
                          <div className="flex gap-[1.5px]">
                            {m.items.map((it, ii) => (
                              <div
                                key={ii}
                                className={`h-2.5 rounded-[1.5px] ${
                                  it.done
                                    ? complete ? "bg-mc-green" : isActive ? "bg-mc-accent" : "bg-mc-text-3"
                                    : "bg-mc-surface-3 opacity-40"
                                }`}
                                style={{ width: Math.max(3, Math.min(8, 60 / mTotal)) }}
                              />
                            ))}
                          </div>
                          <span
                            className={`text-[11px] font-semibold font-mono min-w-[30px] text-right ${
                              complete ? "text-mc-green" : isActive ? "text-mc-accent" : "text-mc-text-3"
                            }`}
                          >
                            {mDone}/{mTotal}
                          </span>
                          <span className="text-mc-text-3 flex">
                            <Icons.chevDown size={10} color={t.text3} open={isOpen} />
                          </span>
                        </div>
                      </div>

                      {/* Active underline bar when collapsed */}
                      {isActive && !isOpen && (
                        <div
                          className="h-0.5 mx-3.5 mb-2 rounded-[1px]"
                          style={{ background: `linear-gradient(90deg, ${t.accent}, transparent)` }}
                        />
                      )}

                      {/* Expanded items */}
                      {isOpen && (
                        <div className="px-3.5 pb-2.5 animate-[fadeIn_0.15s_ease]">
                          <div className="h-px bg-mc-border-0 mb-2" />
                          {m.items.map((item, ii) => {
                            const isNextItem = !item.done && ii === m.items.findIndex((x) => !x.done) && isActive;
                            const isItemExpanded = expandedItem === item.text;

                            return (
                              <div key={ii}>
                                <div
                                  className={`flex items-center gap-2 py-[5px] px-1 rounded-[5px] ${
                                    isNextItem ? "bg-mc-accent-muted" : ""
                                  } ${item.done ? "cursor-default" : "cursor-pointer"}`}
                                >
                                  {/* Checkbox */}
                                  <div
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleToggleDone(item);
                                    }}
                                    className={`w-[15px] h-[15px] rounded shrink-0 flex items-center justify-center cursor-pointer ${
                                      item.done
                                        ? "bg-mc-green text-white"
                                        : "border-[1.5px] border-mc-border-2"
                                    }`}
                                  >
                                    {item.done && <span className="text-[8px]"><Icons.check size={8} color="#fff" /></span>}
                                  </div>

                                  {/* Item text */}
                                  <div className="flex-1 min-w-0" onClick={() => !item.done && toggleItem(item.text)}>
                                    <span
                                      className={`text-xs ${
                                        item.done ? "text-mc-text-3 line-through opacity-60" : "text-mc-text-1"
                                      }`}
                                    >
                                      <InlineMarkdown>{displayTitle(item.text)}</InlineMarkdown>
                                    </span>
                                  </div>

                                  {/* Action buttons for undone items */}
                                  {!item.done && (
                                    <div className="flex gap-1 shrink-0">
                                      <Button small onClick={() => toggleItem(item.text)}>
                                        <Icons.chevDown size={10} color={t.text3} open={isItemExpanded} />
                                      </Button>
                                      <Button primary={isNextItem} small onClick={() => onStartSession?.(item)}>
                                        <Icons.play size={10} /> {isNextItem ? "Start" : "Run"}
                                      </Button>
                                    </div>
                                  )}

                                  {isNextItem && (
                                    <Tag color={t.accent} bg={t.accentMuted}>
                                      Next
                                    </Tag>
                                  )}
                                </div>

                                {/* Expanded item detail */}
                                {isItemExpanded && !item.done && (
                                  <div className="py-2 px-1 pl-[27px] animate-[fadeIn_0.15s_ease]">
                                    <div className="bg-mc-surface-2 border border-mc-border-1 rounded-lg p-3">
                                      {editingItem === item.text ? (
                                        <textarea
                                          value={editText}
                                          onChange={(e) => setEditText(e.target.value)}
                                          className="w-full min-h-[80px] text-[11px] text-mc-text-1 leading-[1.6] font-mono bg-mc-surface-1 border border-mc-accent-border rounded-md p-2.5 resize-y outline-none"
                                          autoFocus
                                        />
                                      ) : (
                                        <pre
                                          className={`text-[11px] leading-[1.6] font-mono whitespace-pre-wrap break-words m-0 ${
                                            item.prompt ? "text-mc-text-2" : "text-mc-text-3 italic"
                                          }`}
                                        >
                                          {item.prompt || `Complete the following task: ${item.text}`}
                                        </pre>
                                      )}

                                      <div className="flex gap-1.5 mt-2.5">
                                        {editingItem === item.text ? (
                                          <>
                                            <Button small onClick={() => setEditingItem(null)}>
                                              Cancel
                                            </Button>
                                            <Button primary small onClick={() => handleSaveEdit(item)}>
                                              <Icons.check size={10} /> Save
                                            </Button>
                                          </>
                                        ) : (
                                          <>
                                            <Button small onClick={() => handleStartEdit(item)}>
                                              <Icons.edit size={10} /> Edit
                                            </Button>
                                            <Button small className="text-mc-text-3" onClick={() => handleSkip(item)}>
                                              Skip
                                            </Button>
                                            <div className="flex-1" />
                                            <Button primary onClick={() => onStartSession?.(item)}>
                                              <Icons.play size={10} /> Start Session
                                            </Button>
                                          </>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        }); })()}
      </div>
    </div>
  );
}
