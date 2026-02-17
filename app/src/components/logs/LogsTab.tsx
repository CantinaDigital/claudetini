import { useState, useEffect, useRef } from "react";
import { Button } from "../ui/Button";
import { Icons } from "../ui/Icons";
import { api, isBackendConnected } from "../../api/backend";
import type { LogEntry } from "../../types";

const LEVELS = ["all", "info", "pass", "warn", "fail"] as const;

const levelStyles: Record<string, { text: string; bg: string }> = {
  info: { text: "text-mc-text-3", bg: "" },
  pass: { text: "text-mc-green", bg: "bg-mc-green-muted" },
  warn: { text: "text-mc-amber", bg: "bg-mc-amber-muted" },
  fail: { text: "text-mc-red", bg: "bg-mc-red-muted" },
};

interface LogsTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  onFix?: (gateName: string, finding: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}

export function LogsTab({ projectPath, isActive = true, onFix, onShowConfirm }: LogsTabProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const hasLoaded = useRef(false);

  // Reset hasLoaded on project change
  useEffect(() => { hasLoaded.current = false; }, [projectPath]);

  useEffect(() => {
    if (!isActive && !hasLoaded.current) return;

    const fetchData = async () => {
      if (!projectPath || !isBackendConnected()) {
        setLogs([]);
        setLoading(false);
        return;
      }

      if (!hasLoaded.current) setLoading(true);
      hasLoaded.current = true;
      setError(null);
      const _t0 = performance.now();
      try {
        const response = await api.getLogs(projectPath);
        setLogs(response.entries || []);
        console.log(`%c[LogsTab] loaded in ${Math.round(performance.now() - _t0)}ms`, "color: #34d399");
      } catch (e) {
        console.warn("Failed to fetch logs:", e);
        setError(e instanceof Error ? e.message : "Failed to load logs");
        setLogs([]);
      } finally {
        setLoading(false);
      }
    };

    void fetchData();
  }, [projectPath, isActive]);

  const filtered = filter === "all" ? logs : logs.filter((l) => l.level === filter);

  const isActionable = (l: LogEntry) =>
    (l.level === "fail" || l.level === "warn") && l.src.startsWith("gate");

  const handleClear = () => {
    if (onShowConfirm) {
      onShowConfirm({
        title: "Clear Logs",
        message: "This will remove all log entries. This cannot be undone.",
        confirmLabel: "Clear All",
        danger: true,
        onConfirm: () => setLogs([]),
      });
    } else {
      setLogs([]);
    }
  };

  const handleFix = (log: LogEntry) => {
    const gateName = log.src.replace("gate:", "").charAt(0).toUpperCase() + log.src.replace("gate:", "").slice(1);
    if (onFix) {
      onFix(gateName, log.msg);
    } else {
      console.log(`Fixing issue from ${log.src}: ${log.msg}`);
    }
  };

  if (loading) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Loading logs...
      </div>
    );
  }

  if (!projectPath) {
    return (
      <div className="text-mc-text-2 p-10 text-center">
        Select a project to view logs.
      </div>
    );
  }

  return (
    <div className="w-full animate-fade-in">
      {error && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-mc-red-muted border border-mc-red-border text-mc-red text-xs">
          {error}
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex justify-between items-center mb-3">
        <div className="flex gap-[3px]">
          {LEVELS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-[10px] py-1 rounded-[5px] border-none cursor-pointer font-mono text-[10.5px] font-semibold uppercase tracking-[0.04em] ${
                filter === f
                  ? "bg-mc-surface-3 text-mc-text-0"
                  : "bg-transparent text-mc-text-3"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          <span className="text-[10px] text-mc-text-3 font-mono">
            {filtered.length}
          </span>
          <Button small onClick={handleClear}>Clear</Button>
        </div>
      </div>

      {/* Log Container */}
      <div className="bg-mc-surface-1 rounded-[10px] border border-mc-border-0 overflow-hidden font-mono text-[11.5px]">
        {filtered.length === 0 ? (
          <div className="py-[30px] px-4 text-center text-mc-text-3 text-xs">
            No log entries found
          </div>
        ) : (
          filtered.map((l, i) => {
            const s = levelStyles[l.level] || levelStyles.info;
            const act = isActionable(l);

            return (
              <div
                key={i}
                className={`flex items-center px-[14px] py-[6px] ${s.bg} ${
                  i < filtered.length - 1 ? "border-b border-mc-border-0" : ""
                }`}
              >
                <span className="text-mc-text-3 w-[88px] shrink-0 opacity-60">
                  {l.time}
                </span>
                <span
                  className={`w-9 shrink-0 font-bold text-[9.5px] uppercase tracking-[0.04em] mt-px ${s.text}`}
                >
                  {l.level}
                </span>
                <span className="text-mc-text-3 w-[100px] shrink-0 opacity-60">
                  {l.src}
                </span>
                <span
                  className={`text-mc-text-1 leading-normal flex-1 ${
                    l.level === "info" ? "opacity-70" : ""
                  }`}
                >
                  {l.msg}
                </span>
                {act && (
                  <button
                    onClick={() => handleFix(l)}
                    className={`inline-flex items-center gap-1 px-[9px] py-[3px] rounded-[5px] cursor-pointer shrink-0 ml-[10px] font-mono text-[10px] font-semibold border-none text-white ${
                      l.level === "fail" ? "bg-mc-red" : "bg-mc-amber"
                    }`}
                  >
                    <Icons.play size={10} /> Fix
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
