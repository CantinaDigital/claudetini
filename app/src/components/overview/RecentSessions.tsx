import { useCallback, useRef, useState } from "react";

interface Session {
  id: string;
  summary: string;
  date: string;
  duration: string;
  cost?: string;
  linesAdded: number;
  linesRemoved: number;
  testsPassed: boolean;
}

interface RecentSessionsProps {
  sessions: Session[];
  onSessionClick: (sessionId: string) => void;
}

export function RecentSessions({ sessions, onSessionClick }: RecentSessionsProps) {
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const visible = sessions.slice(0, 5);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (visible.length === 0) return;
      let next = focusedIndex;

      if (event.key === "ArrowDown") {
        next = Math.min(focusedIndex + 1, visible.length - 1);
      } else if (event.key === "ArrowUp") {
        next = Math.max(focusedIndex - 1, 0);
      } else if (event.key === "Enter" && focusedIndex >= 0) {
        event.preventDefault();
        onSessionClick(visible[focusedIndex].id);
        return;
      } else {
        return;
      }
      event.preventDefault();
      setFocusedIndex(next);
      itemRefs.current[next]?.focus();
    },
    [focusedIndex, visible, onSessionClick],
  );

  if (sessions.length === 0) {
    return (
      <div className="p-4 text-mc-text-3 text-[11px] text-center">
        No recent sessions
      </div>
    );
  }

  return (
    <div className="py-1" role="listbox" aria-label="Recent sessions">
      {visible.map((session, idx) => {
        const isFocused = focusedIndex === idx;
        return (
        <div
          key={session.id}
          ref={(el) => { itemRefs.current[idx] = el; }}
          role="option"
          aria-selected={isFocused}
          tabIndex={isFocused ? 0 : idx === 0 && focusedIndex === -1 ? 0 : -1}
          onClick={() => { setFocusedIndex(idx); onSessionClick(session.id); }}
          onFocus={() => setFocusedIndex(idx)}
          onKeyDown={handleKeyDown}
          className={`flex items-start gap-2.5 py-2.5 px-3.5 cursor-pointer transition-colors duration-100 outline-none hover:bg-mc-surface-1 ${
            idx < visible.length - 1 ? "border-b border-mc-border-0" : ""
          } ${isFocused ? "bg-mc-surface-1" : ""}`}
        >
          {/* Status dot */}
          <div
            className={`w-1.5 h-1.5 rounded-full mt-[5px] shrink-0 ${
              session.testsPassed ? "bg-mc-green" : "bg-mc-red"
            }`}
          />

          {/* Session info */}
          <div className="flex-1 min-w-0">
            <div className="text-[11.5px] font-medium text-mc-text-1 leading-[1.4] truncate">
              {session.summary}
            </div>
            <div className="flex items-center gap-1.5 mt-[3px] text-[10px] font-mono text-mc-text-3">
              <span>#{session.id.slice(-4)}</span>
              <span>{session.duration}</span>
              {session.cost && (
                <span className="text-mc-accent">{session.cost}</span>
              )}
              <span className="text-mc-green">+{session.linesAdded}</span>
              <span className="text-mc-red">-{session.linesRemoved}</span>
            </div>
          </div>

          {/* Date */}
          <div className="text-[9.5px] text-mc-text-3 shrink-0 font-mono mt-0.5">
            {session.date}
          </div>
        </div>
        );
      })}
    </div>
  );
}
