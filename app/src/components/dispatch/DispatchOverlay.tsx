import { useState } from "react";
import { useDispatchManager } from "../../managers/dispatchManager";
import { StreamingOutput } from "./StreamingOutput";
import { DiffBlock, looksLikeDiff } from "../ui/DiffBlock";

function secondsToDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

interface DispatchOverlayProps {
  onRetry: () => void;
}

/**
 * Full-screen overlay showing dispatch progress, errors, and results.
 * Appears when a dispatch job is running or has failed.
 */
export function DispatchOverlay({ onRetry }: DispatchOverlayProps) {
  const [isCancelling, setIsCancelling] = useState(false);
  const isDispatching = useDispatchManager((s) => s.isDispatching);
  const isStreaming = useDispatchManager((s) => s.isStreaming);
  const streamOutputLines = useDispatchManager((s) => s.streamOutputLines);
  const dispatchFailed = useDispatchManager((s) => s.dispatchFailed);
  const showOverlay = useDispatchManager((s) => s.showOverlay);
  const progressPct = useDispatchManager((s) => s.progressPct);
  const elapsedSeconds = useDispatchManager((s) => s.elapsedSeconds);
  const jobId = useDispatchManager((s) => s.jobId);
  const promptPreview = useDispatchManager((s) => s.promptPreview);
  const statusText = useDispatchManager((s) => s.statusText);
  const errorDetail = useDispatchManager((s) => s.errorDetail);
  const outputTail = useDispatchManager((s) => s.outputTail);
  const logFile = useDispatchManager((s) => s.logFile);
  const closeOverlay = useDispatchManager((s) => s.closeOverlay);
  const cancelAction = useDispatchManager((s) => s.cancel);
  const lastContext = useDispatchManager((s) => s.lastContext);

  // Output lines from the manager's output tailing (integrated into pollDispatchJob)
  const outputLines = outputTail ? outputTail.split("\n") : [];

  const handleTryFallback = () => {
    if (lastContext?.prompt) {
      closeOverlay();
      // Trigger fallback via manager state
      useDispatchManager.setState({
        showFallbackModal: true,
        fallbackPrompt: lastContext.prompt,
        fallbackOutput: outputTail,
        fallbackError: errorDetail,
        fallbackErrorCode: null,
        fallbackJobId: null,
        fallbackStatusText: "",
        fallbackPhase: "idle",
        isDispatching: false,
        startedAt: null,
        elapsedSeconds: 0,
        jobId: null,
        promptPreview: "",
        statusText: "",
        progressPct: 0,
        showOverlay: false,
      });
    }
  };

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await cancelAction();
    } finally {
      setIsCancelling(false);
    }
  };

  const diffLineClass = (line: string): string => {
    if (line.startsWith("diff --git")) return "text-mc-text-3 font-bold";
    if (line.startsWith("@@")) return "text-mc-cyan";
    if (line.startsWith("+")) return "text-mc-green";
    if (line.startsWith("-")) return "text-mc-red";
    return "";
  };

  if (!showOverlay || (!isDispatching && !dispatchFailed)) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[9998]">
      <div className="bg-mc-surface-1 rounded-xl px-8 py-6 text-center border border-mc-border-1 w-[520px] max-w-[90vw]">
        {/* Header with spinner or error icon */}
        <div className="flex items-center justify-center gap-2.5 mb-2">
          {isDispatching ? (
            <span className="w-3.5 h-3.5 rounded-full border-2 border-mc-border-1 border-t-mc-accent animate-[cc-spin_0.9s_linear_infinite] inline-block" />
          ) : (
            <span className="text-mc-red text-base">×</span>
          )}
          <div className="text-lg text-mc-text-1 font-bold">
            {isDispatching
              ? isStreaming
                ? "Streaming Claude Code..."
                : "Running Claude Code..."
              : "Dispatch Failed"}
          </div>
        </div>

        {/* Status text */}
        <div className="text-xs text-mc-text-3 mb-2.5">
          {statusText ||
            (isDispatching ? "Processing task..." : "Dispatch ended with an error.")}
        </div>

        {/* Progress bar */}
        <div className="h-2 rounded-full bg-mc-surface-3 overflow-hidden mb-2.5">
          <div
            className={`h-full transition-[width] duration-[250ms] ease-in-out ${
              dispatchFailed ? "bg-mc-red" : "bg-mc-accent"
            }`}
            style={{ width: `${Math.max(3, Math.min(100, progressPct))}%` }}
          />
        </div>

        {/* Elapsed time and job ID */}
        <div className="text-[11px] text-mc-text-3 mb-2.5">
          Elapsed: {secondsToDuration(elapsedSeconds)}
          {jobId ? ` • Job: ${jobId}` : ""}
        </div>

        {/* Prompt preview */}
        <div className="text-[11px] text-mc-text-2 bg-mc-surface-2 border border-mc-border-0 rounded-lg px-2.5 py-2 text-left mb-2 max-h-24 overflow-y-auto">
          {promptPreview}
        </div>

        {/* Streaming output (shown during SSE streaming) */}
        {isDispatching && isStreaming && streamOutputLines.length > 0 && (
          <div className="mb-2.5">
            <StreamingOutput maxHeight={200} showLineNumbers={false} />
          </div>
        )}

        {/* Live CLI output (tailing the actual output file) */}
        {isDispatching && !isStreaming && (
          <div className="text-[10px] font-mono text-mc-text-2 bg-mc-surface-0 border border-mc-border-0 rounded-lg px-2.5 py-2 text-left whitespace-pre-wrap mb-2.5 max-h-[200px] overflow-y-auto">
            <div className="text-[9px] text-mc-text-3 mb-1.5 uppercase tracking-[0.5px] font-bold">
              Live Output
            </div>
            {outputLines.length > 0 ? (
              <div>
                {outputLines.slice(-20).map((line, i) => (
                  <div key={i} className={`mb-0.5 ${diffLineClass(line)}`}>
                    {line}
                  </div>
                ))}
              </div>
            ) : outputTail ? (
              <div>
                {outputTail.split("\n").slice(-20).map((line, i) => (
                  <div key={i} className={`mb-0.5 ${diffLineClass(line)}`}>
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-mc-accent animate-pulse shrink-0" />
                <span className="text-mc-text-3">
                  {statusText || "Waiting for Claude Code output..."}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Error details (only shown when failed) */}
        {dispatchFailed && (
          <>
            {errorDetail && (
              <div className="text-[11px] text-mc-red bg-mc-red-muted border border-mc-red-border rounded-lg px-2.5 py-2 text-left whitespace-pre-wrap mb-2 max-h-40 overflow-y-auto">
                {errorDetail}
              </div>
            )}
            {outputTail && (
              looksLikeDiff(outputTail) ? (
                <div className="mb-2">
                  <DiffBlock text={outputTail} maxHeight={160} />
                </div>
              ) : (
                <div className="text-[11px] text-mc-text-2 bg-mc-surface-0 border border-mc-border-0 rounded-lg px-2.5 py-2 text-left whitespace-pre-wrap mb-2 max-h-40 overflow-y-auto">
                  {outputTail}
                </div>
              )
            )}
            {logFile && (
              <div className="text-[10.5px] text-mc-text-3 mb-2.5 text-left">
                Log file: {logFile}
              </div>
            )}
            <div className="flex justify-center gap-2">
              <button
                onClick={onRetry}
                className="border border-mc-accent rounded-md bg-mc-accent-muted text-mc-text-1 text-[11px] px-3 py-1.5 cursor-pointer"
              >
                Retry dispatch
              </button>
              <button
                onClick={handleTryFallback}
                className="border border-mc-amber rounded-md bg-mc-amber-muted text-mc-amber text-[11px] px-3 py-1.5 cursor-pointer"
              >
                Try Codex/Gemini
              </button>
              <button
                onClick={closeOverlay}
                className="border border-mc-border-1 rounded-md bg-transparent text-mc-text-2 text-[11px] px-3 py-1.5 cursor-pointer"
              >
                Close
              </button>
            </div>
          </>
        )}

        {/* Cancel and Hide buttons (only shown when running) */}
        {isDispatching && (
          <div className="flex justify-center gap-2">
            <button
              onClick={handleCancel}
              disabled={isCancelling}
              className={`border border-mc-red rounded-md bg-mc-red-muted text-mc-red text-[11px] px-2.5 py-[5px] ${
                isCancelling ? "cursor-not-allowed opacity-60" : "cursor-pointer opacity-100"
              }`}
            >
              {isCancelling ? "Cancelling..." : "Cancel"}
            </button>
            <button
              onClick={() => useDispatchManager.setState({ showOverlay: false })}
              className="border border-mc-border-1 rounded-md bg-transparent text-mc-text-2 text-[11px] px-2.5 py-[5px] cursor-pointer"
            >
              Hide
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
