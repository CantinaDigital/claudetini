import { Component, useEffect, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { api, isBackendConnected } from "../../api/backend";
import { useDispatchManager } from "../../managers/dispatchManager";
import { useSettingsStore } from "../../stores/settingsStore";
import type { LiveSession, Exchange, QueuedDispatch } from "../../types";

/**
 * Error boundary to prevent LiveFeed crashes from taking down the entire app.
 */
class LiveFeedErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn("LiveFeed error caught by boundary:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg bg-mc-surface-0 border border-mc-border-0 px-3.5 py-2.5 flex items-center gap-2">
          <span className="text-[11px] text-mc-text-3">
            Live session feed unavailable
          </span>
          <Button
            small
            onClick={() => this.setState({ hasError: false })}
          >
            Retry
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface LiveFeedProps {
  projectPath: string;
  onReport?: (sessionId?: string) => void;
  onDispatchFromQueue?: (item: QueuedDispatch) => void;
}

/** Map a raw backend session (snake_case) to our camelCase LiveSession type. */
function mapSession(raw: Record<string, unknown>): LiveSession {
  return {
    active: true,
    sessionId: (raw.session_id ?? raw.sessionId) as string | undefined,
    provider: (raw.provider as string) || "claude",
    pid: (raw.pid as number | undefined) ?? undefined,
    startedAt: (raw.started_at ?? raw.startedAt) as string | undefined,
    elapsed: (raw.elapsed as string | undefined) ?? undefined,
    estimatedCost: (raw.estimated_cost ?? raw.estimatedCost) as string | undefined,
    tokensUsed: (raw.tokens_used ?? raw.tokensUsed ?? 0) as number,
    filesModified: (raw.files_modified ?? raw.filesModified ?? []) as string[],
    linesAdded: (raw.lines_added ?? raw.linesAdded ?? 0) as number,
    linesRemoved: (raw.lines_removed ?? raw.linesRemoved ?? 0) as number,
  };
}

function formatTime(timeString: string): string {
  try {
    const date = new Date(timeString);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return timeString;
  }
}

function ExchangeRow({ exchange }: { exchange: Exchange }) {
  const isUser = exchange.type === "user";

  return (
    <div className="flex gap-2.5 py-2 border-b border-mc-border-0">
      {/* Time column */}
      <div className="w-14 shrink-0 text-[10px] font-mono text-mc-text-3">
        {formatTime(exchange.time)}
      </div>

      {/* 2px vertical bar indicator */}
      <div
        className={`w-0.5 min-h-[16px] rounded-sm shrink-0 mt-0.5 ${
          isUser ? "bg-mc-accent" : "bg-mc-green"
        }`}
      />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div
          className={`text-[11px] leading-[1.4] ${
            isUser ? "text-mc-text-1 font-semibold" : "text-mc-text-2 font-normal"
          }`}
        >
          <span className="font-mono text-mc-text-3 mr-1">
            {isUser ? "\u2192" : "\u2190"}
          </span>
          {exchange.summary}
        </div>

        {/* File pills */}
        {exchange.files && exchange.files.length > 0 && (
          <div className="flex gap-1 flex-wrap mt-1">
            {exchange.files.slice(0, 3).map((file, i) => (
              <Tag key={i} color={t.text3} bg={t.surface2}>
                {file.split("/").pop()}
              </Tag>
            ))}
            {exchange.files.length > 3 && (
              <Tag color={t.text3} bg={t.surface2}>
                +{exchange.files.length - 3} more
              </Tag>
            )}
          </div>
        )}

        {/* Lines changed */}
        {exchange.lines && (
          <div className="text-[9px] font-mono text-mc-text-3 mt-0.5">
            {exchange.lines}
          </div>
        )}
      </div>
    </div>
  );
}

function LiveFeedHeader({
  session,
  sessionCount,
  expanded,
  onToggle,
}: {
  session: LiveSession;
  sessionCount: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-2.5 px-3.5 py-2.5 cursor-pointer ${
        expanded ? "border-b border-mc-border-0" : ""
      }`}
      onClick={onToggle}
    >
      {/* Pulsing green dot */}
      <div
        className="w-[7px] h-[7px] rounded-full bg-mc-green animate-pulse shrink-0"
        style={{ boxShadow: `0 0 8px ${t.green}` }}
      />

      {/* LIVE SESSION label + count */}
      <span className="text-[11px] font-bold font-mono text-mc-green uppercase tracking-[0.08em] shrink-0">
        {sessionCount > 1 ? `${sessionCount} LIVE SESSIONS` : "LIVE SESSION"}
      </span>

      {session.provider && (
        <Tag color={t.accent} bg={t.accentMuted}>{session.provider}</Tag>
      )}

      {session.pid && (
        <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
          PID {session.pid}
        </span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Elapsed time */}
      <span className="text-[11px] font-mono text-mc-text-1 font-semibold shrink-0">
        {session.elapsed || "0s"}
      </span>

      {/* Cost */}
      {session.estimatedCost && (
        <>
          <div className="w-px h-3.5 bg-mc-border-1 shrink-0" />
          <span className="text-[10px] font-mono text-mc-accent shrink-0">
            {session.estimatedCost}
          </span>
        </>
      )}

      {/* Lines added/removed */}
      {((session.linesAdded ?? 0) > 0 || (session.linesRemoved ?? 0) > 0) && (
        <>
          <div className="w-px h-3.5 bg-mc-border-1 shrink-0" />
          <span className="text-[10px] font-mono shrink-0">
            <span className="text-mc-green">+{session.linesAdded ?? 0}</span>
            {" "}
            <span className="text-mc-red">-{session.linesRemoved ?? 0}</span>
          </span>
        </>
      )}

      {/* Files count */}
      {(session.filesModified?.length ?? 0) > 0 && (
        <>
          <div className="w-px h-3.5 bg-mc-border-1 shrink-0" />
          <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
            {session.filesModified.length} file{session.filesModified.length !== 1 ? "s" : ""}
          </span>
        </>
      )}

      {/* Collapse/Expand button */}
      <Button
        small
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
      >
        {expanded ? "Collapse" : "Expand"}
      </Button>
    </div>
  );
}

function CollapsedSummary({
  session,
  exchanges,
}: {
  session: LiveSession;
  exchanges: Exchange[];
}) {
  const lastExchange = exchanges.length > 0 ? exchanges[exchanges.length - 1] : null;

  if (!lastExchange) {
    return (
      <div className="px-4 py-2 text-[11px] text-mc-text-2 flex items-center gap-2">
        <span>{session.filesModified?.length ?? 0} files modified</span>
        <span className="text-mc-green">+{session.linesAdded ?? 0}</span>
        <span className="text-mc-red">-{session.linesRemoved ?? 0}</span>
      </div>
    );
  }

  return (
    <div className="px-4 py-2 flex items-center gap-2.5">
      <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
        {formatTime(lastExchange.time)}
      </span>
      <div
        className={`w-0.5 h-3.5 rounded-sm shrink-0 ${
          lastExchange.type === "user" ? "bg-mc-accent" : "bg-mc-green"
        }`}
      />
      <span className="text-[11.5px] text-mc-text-1 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
        {lastExchange.type === "user" ? "\u2192 " : "\u2190 "}
        {lastExchange.summary}
      </span>
      <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
        {exchanges.length} exchange{exchanges.length !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

function ModifiedFilesStrip({ files }: { files: string[] }) {
  if (files.length === 0) return null;

  return (
    <div className="px-3.5 py-2 border-t border-mc-border-0 flex items-center gap-1.5 overflow-x-auto">
      <span className="text-[9px] font-semibold text-mc-text-3 shrink-0">
        MODIFIED:
      </span>
      {files.slice(0, 5).map((file, i) => (
        <button
          key={i}
          className="bg-mc-surface-2 border border-mc-border-1 rounded px-1.5 py-0.5 text-[9px] font-mono text-mc-accent cursor-pointer whitespace-nowrap"
          title={file}
        >
          {file.split("/").pop()}
        </button>
      ))}
      {files.length > 5 && (
        <span className="text-[9px] text-mc-text-3">+{files.length - 5} more</span>
      )}
    </div>
  );
}

function SessionEndedState({
  session,
  onReport,
  onDismiss,
}: {
  session: LiveSession;
  onReport?: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="p-3.5 flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <div className="w-2.5 h-2.5 rounded-full bg-mc-text-3" />
        <span className="text-[11px] font-semibold text-mc-text-2">
          SESSION ENDED
        </span>
        {session.elapsed && (
          <span className="text-[10px] font-mono text-mc-text-3">
            Duration: {session.elapsed}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <Button small primary onClick={onReport}>
          View Report
        </Button>
        <Button small onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

/** Compact row for secondary sessions (not the primary/expanded one). */
function SecondarySessionRow({ session }: { session: LiveSession }) {
  return (
    <div className="flex items-center gap-2 px-3.5 py-1.5 border-t border-mc-border-0">
      <div
        className="w-[5px] h-[5px] rounded-full bg-mc-green animate-pulse shrink-0"
        style={{ boxShadow: `0 0 6px ${t.green}` }}
      />
      <span className="text-[10px] font-mono text-mc-text-2 shrink-0">
        {session.sessionId?.slice(0, 8) ?? "session"}
      </span>
      {session.provider && (
        <Tag color={t.text3} bg={t.surface2}>{session.provider}</Tag>
      )}
      <div className="flex-1" />
      <span className="text-[10px] font-mono text-mc-text-1 font-semibold">
        {session.elapsed || "0s"}
      </span>
      {session.estimatedCost && (
        <>
          <div className="w-px h-3 bg-mc-border-1" />
          <span className="text-[10px] font-mono text-mc-accent">
            {session.estimatedCost}
          </span>
        </>
      )}
      {(session.filesModified?.length ?? 0) > 0 && (
        <>
          <div className="w-px h-3 bg-mc-border-1" />
          <span className="text-[10px] font-mono text-mc-text-3">
            {session.filesModified.length} file{session.filesModified.length !== 1 ? "s" : ""}
          </span>
        </>
      )}
    </div>
  );
}

function getRelativeTime(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function QueuedItemRow({
  item,
  index,
  isDispatching,
  onDispatch,
  onRemove,
}: {
  item: QueuedDispatch;
  index: number;
  isDispatching: boolean;
  onDispatch: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2.5 px-3.5 py-2 border-b border-mc-border-0">
      {/* Position number */}
      <span className="text-[10px] font-bold font-mono text-mc-text-3 w-5 text-center shrink-0">
        {index + 1}
      </span>

      {/* Prompt text */}
      <span className="text-[11.5px] text-mc-text-1 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
        {item.prompt}
      </span>

      {/* Time ago */}
      <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
        {getRelativeTime(item.queuedAt)}
      </span>

      {/* Dispatch button */}
      <Button small primary onClick={onDispatch} disabled={isDispatching}>
        Dispatch
      </Button>

      {/* Remove button */}
      <button
        onClick={onRemove}
        className="bg-transparent border-none text-mc-text-3 cursor-pointer px-1 py-0.5 text-sm leading-none"
        title="Remove from queue"
      >
        {"\u00D7"}
      </button>
    </div>
  );
}

function LiveFeedInner({ projectPath, onReport, onDispatchFromQueue }: LiveFeedProps) {
  // Queue state from dispatch manager
  const queue = useDispatchManager((s) => s.queue);
  const removeFromQueue = useDispatchManager((s) => s.removeFromQueue);
  const isDispatching = useDispatchManager((s) => s.isDispatching);

  const [liveSessions, setLiveSessions] = useState<LiveSession[]>([]);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [feedExpanded, setFeedExpanded] = useState(true);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [lastEndedSession, setLastEndedSession] = useState<LiveSession | null>(null);
  const exchangeLogRef = useRef<HTMLDivElement>(null);
  const prevSessionIds = useRef<Set<string>>(new Set());
  const pollInFlight = useRef(false);

  // Poll backend for live sessions.
  // 2s when sessions are active, 15s when idle, stop when dismissed.
  useEffect(() => {
    if (!projectPath || !isBackendConnected() || (dismissed && queue.length === 0)) {
      return;
    }

    let cancelled = false;
    let autoDispatchTimer: ReturnType<typeof setTimeout> | null = null;
    const hasActiveSessions = liveSessions.length > 0 && !sessionEnded;
    const pollRate = hasActiveSessions ? 2000 : 15000;

    const poll = async () => {
      if (pollInFlight.current) return;
      pollInFlight.current = true;
      try {
        const response = await api.getLiveSessions(projectPath);

        if (cancelled) return;

        if (response.active) {
          // Map all sessions (prefer `sessions` array, fall back to single `session`)
          const responseAny = response as unknown as Record<string, unknown>;
          const rawSessions: Record<string, unknown>[] = Array.isArray(responseAny.sessions)
            ? (responseAny.sessions as Record<string, unknown>[])
            : responseAny.session
              ? [responseAny.session as Record<string, unknown>]
              : [];

          const mapped = rawSessions.map(mapSession);

          if (mapped.length > 0) {
            // Track session IDs to detect new sessions
            const currentIds = new Set(mapped.map((s) => s.sessionId).filter(Boolean) as string[]);
            for (const id of currentIds) {
              if (!prevSessionIds.current.has(id)) {
                // New session appeared — reset ended/dismissed state
                setSessionEnded(false);
                setDismissed(false);
              }
            }
            prevSessionIds.current = currentIds;

            setLiveSessions(mapped);
            setExchanges(response.exchanges);
          }
        } else {
          // No active sessions
          if (liveSessions.length > 0 && !sessionEnded) {
            // Sessions just ended
            setLastEndedSession(liveSessions[0]);
            setSessionEnded(true);

            // Auto-dispatch next queued item after a brief delay
            const currentQueue = useDispatchManager.getState().queue;
            const currentIsDispatching = useDispatchManager.getState().isDispatching;
            const currentAutoDispatch = useSettingsStore.getState().autoDispatchEnabled;
            if (currentAutoDispatch && currentQueue.length > 0 && !currentIsDispatching) {
              autoDispatchTimer = setTimeout(() => {
                useDispatchManager.getState().dispatchNext(projectPath);
              }, 2000);
            }
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "";
        if (
          message.includes("/api/live-sessions/") &&
          message.includes("Request timed out while calling")
        ) {
          return;
        }
        console.warn("Failed to poll live sessions:", error);
      } finally {
        pollInFlight.current = false;
      }
    };

    // Initial poll
    void poll();

    // Set up interval — fast when active, slow when idle
    const interval = setInterval(poll, pollRate);

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (autoDispatchTimer !== null) {
        clearTimeout(autoDispatchTimer);
      }
    };
  }, [projectPath, liveSessions.length, sessionEnded, dismissed, queue.length]);

  // Auto-scroll exchange log to bottom on new exchanges
  useEffect(() => {
    if (exchangeLogRef.current && feedExpanded) {
      exchangeLogRef.current.scrollTop = exchangeLogRef.current.scrollHeight;
    }
  }, [exchanges, feedExpanded]);

  // Don't render if dismissed AND no queue, or no session data AND no queue
  if (dismissed && queue.length === 0) return null;
  if (liveSessions.length === 0 && !sessionEnded && queue.length === 0) return null;

  // Helper to render queued items section
  const renderQueue = (header: string) => {
    if (queue.length === 0) return null;
    return (
      <div>
        <div className="px-3.5 py-1.5 text-[9px] font-bold font-mono text-mc-amber uppercase tracking-[0.08em] border-t border-mc-border-0">
          {header} ({queue.length})
        </div>
        {queue.map((item, i) => (
          <QueuedItemRow
            key={item.id}
            item={item}
            index={i}
            isDispatching={isDispatching}
            onDispatch={() => {
              removeFromQueue(item.id);
              onDispatchFromQueue?.(item);
            }}
            onRemove={() => removeFromQueue(item.id)}
          />
        ))}
      </div>
    );
  };

  // Session ended state — show ended banner + queue
  const endedSession = lastEndedSession ?? liveSessions[0];
  if (sessionEnded && endedSession) {
    return (
      <div className="rounded-lg bg-mc-surface-0 border border-mc-border-1 overflow-hidden">
        <SessionEndedState
          session={endedSession}
          onReport={() => onReport?.(endedSession.sessionId || undefined)}
          onDismiss={() => {
            setDismissed(true);
            setLiveSessions([]);
            setLastEndedSession(null);
          }}
        />
        {renderQueue("NEXT UP")}
      </div>
    );
  }

  // No active sessions but queue has items — standalone queue card
  if (liveSessions.length === 0) {
    if (queue.length === 0) return null;
    return (
      <div className="rounded-lg bg-mc-surface-0 border border-mc-border-0 overflow-hidden animate-fade-in">
        {renderQueue("DISPATCH QUEUE")}
      </div>
    );
  }

  const primarySession = liveSessions[0];
  const secondarySessions = liveSessions.slice(1);

  return (
    <div className="rounded-xl bg-mc-surface-1 border border-mc-green-border overflow-hidden animate-fade-in">
      <LiveFeedHeader
        session={primarySession}
        sessionCount={liveSessions.length}
        expanded={feedExpanded}
        onToggle={() => setFeedExpanded(!feedExpanded)}
      />

      {feedExpanded ? (
          <div
            ref={exchangeLogRef}
            className="max-h-80 overflow-y-auto px-3.5"
          >
            {exchanges.length === 0 ? (
              <div className="py-3 text-[11px] text-mc-text-3">
                Waiting for activity...
              </div>
            ) : (
              exchanges.map((exchange, i) => (
                <ExchangeRow key={i} exchange={exchange} />
              ))
            )}
          </div>
      ) : (
        <CollapsedSummary session={primarySession} exchanges={exchanges} />
      )}

      {/* Secondary sessions — compact rows */}
      {secondarySessions.length > 0 && (
        <div className="border-t border-mc-border-0">
          <div className="px-3.5 pt-1 pb-0.5 text-[9px] font-mono text-mc-text-3 uppercase">
            + {secondarySessions.length} other session{secondarySessions.length !== 1 ? "s" : ""}
          </div>
          {secondarySessions.map((s, i) => (
            <SecondarySessionRow key={s.sessionId ?? i} session={s} />
          ))}
        </div>
      )}

      {/* Modified files strip — always visible in both expanded and collapsed */}
      <ModifiedFilesStrip files={primarySession.filesModified ?? []} />

      {/* Queue section below active sessions */}
      {renderQueue("NEXT UP")}
    </div>
  );
}

export function LiveFeed(props: LiveFeedProps) {
  return (
    <LiveFeedErrorBoundary>
      <LiveFeedInner {...props} />
    </LiveFeedErrorBoundary>
  );
}
