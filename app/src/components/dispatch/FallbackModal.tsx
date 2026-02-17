import { t } from "../../styles/tokens";
import { Button } from "../ui/Button";
import type { FallbackProvider } from "../../stores/settingsStore";

interface FallbackModalProps {
  prompt: string;
  preferredProvider: FallbackProvider;
  isRunning: boolean;
  runningProvider: FallbackProvider | null;
  output?: string | null;
  error?: string | null;
  errorCode?: string | null;
  statusText?: string | null;
  phase?: string | null;
  onRun: (provider: FallbackProvider) => void;
  onClose: () => void;
}

export function FallbackModal({
  prompt,
  preferredProvider,
  isRunning,
  runningProvider,
  output,
  error,
  errorCode,
  statusText,
  phase,
  onRun,
  onClose,
}: FallbackModalProps) {
  const runningLabel = runningProvider ? runningProvider.toUpperCase() : "provider";

  return (
    <div
      className="fixed inset-0 bg-black/60 z-[240] flex items-center justify-center"
      onClick={() => !isRunning && onClose()}
    >
      <div
        className="w-[640px] max-w-[92vw] bg-mc-surface-1 rounded-xl border border-mc-border-1 overflow-hidden animate-fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-mc-border-0">
          <div className="flex items-center gap-2.5">
            {isRunning && (
              <span
                className="w-3.5 h-3.5 rounded-full border-2 border-mc-border-1 shrink-0 inline-block"
                style={{ borderTopColor: t.cyan, animation: "cc-spin 0.9s linear infinite" }}
              />
            )}
            <div className={`text-sm font-bold ${isRunning ? "text-mc-cyan" : "text-mc-text-0"}`}>
              {isRunning
                ? `Running via ${runningLabel}...`
                : "Claude Code token limit reached"}
            </div>
          </div>
          <div className="text-xs text-mc-text-2 mt-1">
            {isRunning
              ? "This may take a few minutes. Please wait."
              : "Run this task with an alternative?"}
          </div>
          {(isRunning || statusText) && (
            <div className="mt-1.5 text-[11px] text-mc-cyan font-mono">
              {statusText || "Running fallback dispatch..."}
              {phase ? ` [${phase}]` : ""}
            </div>
          )}
          <div className="mt-2.5 text-[10.5px] text-mc-text-3 font-mono whitespace-pre-wrap bg-mc-surface-0 rounded-lg border border-mc-border-0 py-2 px-2.5">
            {prompt}
          </div>
        </div>

        <div className="px-5 pt-3 pb-[18px]">
          <div className="flex gap-2 mb-3">
            <Button
              primary={preferredProvider === "codex"}
              disabled={isRunning}
              onClick={() => onRun("codex")}
            >
              {isRunning && runningProvider === "codex" ? "Running..." : "Run via Codex"}
            </Button>
            <Button
              primary={preferredProvider === "gemini"}
              disabled={isRunning}
              onClick={() => onRun("gemini")}
            >
              {isRunning && runningProvider === "gemini" ? "Running..." : "Run via Gemini"}
            </Button>
            <div className="flex-1" />
            <Button disabled={isRunning} onClick={onClose}>
              Close
            </Button>
          </div>

          {error && (
            <div className={`text-xs text-mc-red bg-mc-red-muted border border-mc-red-border rounded-lg py-2 px-2.5 ${output ? "mb-2.5" : ""}`}>
              {errorCode ? `${errorCode}: ${error}` : error}
            </div>
          )}

          {output && (
            <pre className="m-0 max-h-[260px] overflow-auto rounded-lg border border-mc-border-0 bg-mc-surface-0 text-mc-text-2 py-2.5 px-3 font-mono text-[11px] whitespace-pre-wrap break-words">
              {output}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
