import { useState, useRef } from "react";
import { t } from "../../styles/tokens";
import { Icons } from "../ui/Icons";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { SeverityTag } from "../ui/SeverityTag";
import { Select } from "../ui/Select";
import { InlineMarkdown } from "../ui/InlineMarkdown";
import { api, isBackendConnected } from "../../api/backend";
import type { DispatchAdvice, PromptHistoryEntry, RetryChainEntry } from "../../types";

interface MilestoneItem {
  text: string;
  done: boolean;
  prompt?: string;
  context?: string;
  promptHistory?: PromptHistoryEntry[];
  retryChain?: RetryChainEntry[];
}

interface Milestone {
  id: number;
  phase: string;
  title: string;
  sprint: string;
  items: MilestoneItem[];
}

interface MilestoneCardProps {
  milestone: Milestone;
  expandedItem: string | null;
  onExpandItem: (text: string | null) => void;
  projectPath?: string | null;
  usageMode?: "subscription" | "api";
  taskAdvice?: Record<string, DispatchAdvice>;
  onStartSession?: (item: MilestoneItem) => void;
  onToggleDone?: (item: MilestoneItem) => void;
  onRetryWithContext?: (item: MilestoneItem, retryPrompt: string) => void;
  onEditPrompt?: (item: MilestoneItem, newPrompt: string) => void;
}

export function MilestoneCard({
  milestone,
  expandedItem,
  onExpandItem,
  projectPath,
  usageMode = "subscription",
  taskAdvice = {},
  onStartSession,
  onToggleDone,
  onRetryWithContext,
  onEditPrompt,
}: MilestoneCardProps) {
  const [promptVersion, setPromptVersion] = useState<Record<string, number>>({});
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [editText, setEditText] = useState<string>("");
  const [aiPrompts, setAiPrompts] = useState<Record<string, string>>({});
  const [generatingPrompt, setGeneratingPrompt] = useState<string | null>(null);
  const generatedKeys = useRef<Set<string>>(new Set());

  const remaining = milestone.items.filter((i) => !i.done);
  const completed = milestone.items.filter((i) => i.done).length;
  const total = milestone.items.length;
  const progress = Math.round((completed / total) * 100);

  const handleStart = (item: MilestoneItem) => {
    onStartSession?.(item);
  };

  const handleToggleDone = (item: MilestoneItem) => {
    onToggleDone?.(item);
  };

  const handleRetry = (item: MilestoneItem) => {
    if (!item.retryChain || item.retryChain.length === 0) return;

    const lastAttempt = item.retryChain[item.retryChain.length - 1];
    const retryPrompt = `Previous attempt failed with: "${lastAttempt.error}"

The task was: ${item.text}

Try a different approach to complete this task. Focus on avoiding the previous error.`;

    if (onRetryWithContext) {
      onRetryWithContext(item, retryPrompt);
    } else {
      // Fallback: just start with the retry prompt as the item prompt
      onStartSession?.({ ...item, prompt: retryPrompt });
    }
  };

  const handleStartEdit = (item: MilestoneItem) => {
    const pv = promptVersion[item.text] || (item.promptHistory ? item.promptHistory.length : 1);
    const curPrompt = item.promptHistory?.find((h) => h.v === pv);
    setEditingItem(item.text);
    setEditText(curPrompt?.prompt || item.prompt || `Implement: ${item.text.replace(/^\*\*[\d.]+\*\*\s*/, "")}`);
  };

  const handleSaveEdit = (item: MilestoneItem) => {
    if (editText.trim() && onEditPrompt) {
      onEditPrompt(item, editText.trim());
    }
    setEditingItem(null);
    setEditText("");
  };

  const handleCancelEdit = () => {
    setEditingItem(null);
    setEditText("");
  };

  return (
    <div>
      {/* Header with Sprint Badge */}
      <div className="px-4 pt-3.5 pb-[11px] border-b border-mc-border-0">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            {/* Sprint Number Badge */}
            <div
              className="w-6 h-6 rounded-[7px] flex items-center justify-center text-[11px] font-extrabold font-mono text-white"
              style={{ background: `linear-gradient(135deg, ${t.accent}, ${t.accentDark})` }}
            >
              {milestone.id}
            </div>
            <div>
              <div className="text-[13px] font-bold text-mc-text-0">
                <InlineMarkdown>{milestone.title}</InlineMarkdown>
              </div>
              <div className="text-[9.5px] font-mono text-mc-text-3 uppercase mt-px">
                {milestone.sprint} · {remaining.length} remaining
              </div>
            </div>
          </div>
          {/* Progress bar + percentage */}
          <div className="flex items-center gap-1.5">
            <div className="w-[60px] h-1 bg-mc-surface-3 rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm bg-mc-accent"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="text-[11px] font-bold text-mc-accent font-mono">
              {progress}%
            </span>
          </div>
        </div>
      </div>

      {/* Task Items */}
      <div className="py-1">
        {remaining.map((item, idx) => {
          const isNext = idx === 0;
          const isExpanded = expandedItem === item.text;
          const pv = promptVersion[item.text] || (item.promptHistory ? item.promptHistory.length : 1);
          const curPrompt = item.promptHistory?.find((h) => h.v === pv);
          const advice = taskAdvice[item.text];
          const adviceTokenLabel = `~${((advice?.estimated_tokens ?? 0) / 1000).toFixed(1)}k tok`;
          const adviceSummary =
            usageMode === "api" && advice?.estimated_cost !== undefined && advice?.estimated_cost !== null
              ? `${adviceTokenLabel} · $${advice.estimated_cost.toFixed(2)}`
              : `${adviceTokenLabel} · ${(advice?.estimated_effort_units ?? 0).toFixed(2)}u`;

          return (
            <div
              key={item.text}
              style={{ '--stagger-delay': `${idx * 0.02}s` } as React.CSSProperties}
              className="animate-slide-up [animation-delay:var(--stagger-delay)] [animation-fill-mode:both]"
            >
              {/* Task Row */}
              <div
                onClick={() => {
                  const expanding = !isExpanded;
                  onExpandItem(expanding ? item.text : null);
                  // Trigger AI prompt generation on first expand
                  if (expanding && projectPath && isBackendConnected() && !aiPrompts[item.text] && !generatedKeys.current.has(item.text)) {
                    generatedKeys.current.add(item.text);
                    setGeneratingPrompt(item.text);
                    api.generateTaskPrompt(projectPath, item.text).then((result) => {
                      if (result.ai_generated) {
                        setAiPrompts((prev) => ({ ...prev, [item.text]: result.prompt }));
                      }
                      setGeneratingPrompt((cur) => cur === item.text ? null : cur);
                    }).catch(() => {
                      setGeneratingPrompt((cur) => cur === item.text ? null : cur);
                    });
                  }
                }}
                className={`flex items-center gap-2 cursor-pointer ${
                  isNext
                    ? "py-[9px] px-4 bg-mc-accent-muted border-l-[3px] border-l-mc-accent"
                    : "py-[7px] px-4 border-l-[3px] border-l-transparent"
                }`}
              >
                {/* Checkbox indicator - clickable to mark done */}
                <div
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleDone(item);
                  }}
                  className={`w-3.5 h-3.5 rounded shrink-0 flex items-center justify-center cursor-pointer transition-colors duration-150 ${
                    isNext
                      ? "border-[1.5px] border-mc-accent-border"
                      : "border-[1.5px] border-mc-border-2"
                  }`}
                >
                  {isNext && (
                    <div className="w-1 h-1 rounded-[1.5px] bg-mc-accent" />
                  )}
                </div>

                {/* Task text */}
                <div className="flex-1 min-w-0">
                  <div
                    className={`text-xs overflow-hidden text-ellipsis whitespace-nowrap ${
                      isNext ? "font-semibold text-mc-text-0" : "font-normal text-mc-text-2"
                    }`}
                  >
                    <InlineMarkdown>{item.text}</InlineMarkdown>
                  </div>
                  {isNext && (
                    <div className="text-[9.5px] text-mc-text-3 font-mono mt-px">
                      Up next · click for prompt
                    </div>
                  )}
                  {advice && (
                    <div className="mt-[3px] flex items-center gap-1.5 flex-wrap">
                      <span className="text-[9.5px] text-mc-text-3 font-mono">
                        {adviceSummary}
                      </span>
                      {advice.remaining_pct !== undefined && advice.remaining_pct !== null && (
                        <Tag
                          color={advice.should_suggest_fallback ? t.amber : t.text3}
                          bg={advice.should_suggest_fallback ? t.amberMuted : "transparent"}
                        >
                          {advice.remaining_pct.toFixed(1)}% left
                        </Tag>
                      )}
                      {advice.should_suggest_fallback && (
                        <Tag color={t.amber} bg={t.amberMuted}>
                          Suggest {advice.suggested_provider === "gemini" ? "Gemini" : "Codex"}
                        </Tag>
                      )}
                    </div>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex gap-1 shrink-0">
                  {item.retryChain && item.retryChain.length > 0 && (
                    <Button
                      small
                      className="!text-mc-amber !border-mc-amber-border"
                      onClick={(e: React.MouseEvent) => {
                        e.stopPropagation();
                        handleRetry(item);
                      }}
                    >
                      <Icons.retry size={10} />
                    </Button>
                  )}
                  <Button
                    primary={isNext}
                    small
                    onClick={(e: React.MouseEvent) => {
                      e.stopPropagation();
                      handleStart(item);
                    }}
                  >
                    <Icons.play size={10} /> {isNext ? "Start" : "Run"}
                  </Button>
                </div>
              </div>

              {/* Expanded Claude Prompt Section */}
              {isExpanded && (
                <div className="px-4 pb-2 pl-[41px] animate-fade-in-fastest">
                  <div className="bg-mc-surface-2 border border-mc-border-1 rounded-lg p-3.5 mt-[3px]">
                    {/* Header: Claude Prompt label + version dropdown */}
                    <div className="flex items-center justify-between mb-2">
                      <Tag>Claude Prompt</Tag>
                      {item.promptHistory && item.promptHistory.length > 0 && (
                        <Select
                          value={String(pv)}
                          onChange={(val) =>
                            setPromptVersion((p) => ({
                              ...p,
                              [item.text]: Number(val),
                            }))
                          }
                          small
                          options={item.promptHistory.map((h) => ({
                            value: String(h.v),
                            label: `v${h.v}`,
                            icon: h.outcome === "fail" ? (
                              <span className="text-mc-red">&#10007;</span>
                            ) : h.outcome === "pass" ? (
                              <span className="text-mc-green">&#10003;</span>
                            ) : undefined,
                          }))}
                        />
                      )}
                    </div>

                    {/* Prompt text - editable or read-only */}
                    {editingItem === item.text ? (
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="w-full min-h-[100px] text-[11px] text-mc-text-1 leading-[1.6] font-mono bg-mc-surface-1 border border-mc-accent-border rounded-md p-2.5 resize-y outline-none"
                        autoFocus
                      />
                    ) : generatingPrompt === item.text ? (
                      <div className="py-2">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="w-3 h-3 border-2 border-mc-accent border-t-transparent rounded-full animate-[cc-spin_0.8s_linear_infinite]" />
                          <span className="text-[11px] text-mc-accent font-medium">
                            Claude is analyzing your codebase to generate a prompt...
                          </span>
                        </div>
                        <div className="h-[3px] rounded-sm bg-mc-surface-3 overflow-hidden">
                          <div className="w-[60%] h-full rounded-sm bg-mc-accent animate-pulse" />
                        </div>
                      </div>
                    ) : (
                      <>
                        {aiPrompts[item.text] && (
                          <div className="flex items-center gap-1.5 mb-1.5">
                            <Tag color="#8b7cf6" bg="rgba(139,124,246,0.12)">AI Generated</Tag>
                            <span className="text-[9.5px] text-mc-text-3">by Claude Code</span>
                          </div>
                        )}
                        <pre
                          className={`text-[11px] leading-[1.6] font-mono whitespace-pre-wrap break-words m-0 ${
                            aiPrompts[item.text] || curPrompt?.prompt || item.prompt
                              ? "text-mc-text-2"
                              : "text-mc-text-3 italic"
                          }`}
                        >
                          {aiPrompts[item.text] || curPrompt?.prompt || item.prompt || `Implement: ${item.text.replace(/^\*\*[\d.]+\*\*\s*/, "")}`}
                        </pre>
                      </>
                    )}

                    {/* Outcome banner (if prompt has outcome) */}
                    {curPrompt && curPrompt.outcome && (
                      <div
                        className={`mt-2.5 px-2.5 py-2 rounded-md flex items-center gap-2 border ${
                          curPrompt.outcome === "fail"
                            ? "bg-mc-red-muted border-mc-red-border"
                            : "bg-mc-green-muted border-mc-green-border"
                        }`}
                      >
                        <SeverityTag status={curPrompt.outcome} />
                        <span className="text-[11px] text-mc-text-2 flex-1">
                          {curPrompt.error || "Completed"}
                        </span>
                        <span className="text-[10px] font-mono text-mc-text-3">
                          {curPrompt.cost} · {curPrompt.date}
                        </span>
                      </div>
                    )}

                    {/* Retry Chain */}
                    {item.retryChain && item.retryChain.length > 0 && (
                      <div className="mt-2.5 px-2.5 py-2 rounded-md bg-mc-amber-muted border border-mc-amber-border">
                        <div className="text-[9.5px] font-bold font-mono text-mc-amber uppercase tracking-[0.06em] mb-1">
                          Retry Chain · {item.retryChain.length} attempt
                          {item.retryChain.length > 1 ? "s" : ""}
                        </div>
                        {item.retryChain.map((a, ri) => (
                          <div
                            key={ri}
                            className="text-[10.5px] text-mc-text-2 py-[2px]"
                          >
                            #{a.attempt}:{" "}
                            <span className="text-mc-red">Failed</span> — {a.error}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="flex gap-1.5 mt-3">
                      {editingItem === item.text ? (
                        <>
                          <Button small onClick={handleCancelEdit}>
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
                          {item.retryChain && item.retryChain.length > 0 && (
                            <Button
                              small
                              className="!text-mc-amber !border-mc-amber-border"
                              onClick={() => handleRetry(item)}
                            >
                              <Icons.retry size={10} /> Retry with Context
                            </Button>
                          )}
                          <Button primary onClick={() => handleStart(item)}>
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

      {/* Completed count footer */}
      {completed > 0 && (
        <div className="px-4 py-2 border-t border-mc-border-0 text-[10px] text-mc-text-3 font-mono">
          {completed} completed
        </div>
      )}
    </div>
  );
}
