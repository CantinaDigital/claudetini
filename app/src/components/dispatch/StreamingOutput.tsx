import { useEffect, useRef, useState } from "react";
import { useDispatchManager } from "../../managers/dispatchManager";

interface StreamingOutputProps {
  maxHeight?: number;
  showLineNumbers?: boolean;
}

/**
 * Real-time streaming output display for Claude Code dispatch.
 * Features auto-scroll with scroll lock toggle and line limiting.
 */
export function StreamingOutput({
  maxHeight = 200,
  showLineNumbers = false,
}: StreamingOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [userScrolled, setUserScrolled] = useState(false);

  const streamOutputLines = useDispatchManager((s) => s.streamOutputLines);
  const isStreaming = useDispatchManager((s) => s.isStreaming);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [streamOutputLines, autoScroll]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 30;

    if (!isAtBottom && !userScrolled) {
      setUserScrolled(true);
      setAutoScroll(false);
    } else if (isAtBottom && userScrolled) {
      setUserScrolled(false);
      setAutoScroll(true);
    }
  };

  const toggleAutoScroll = () => {
    setAutoScroll(!autoScroll);
    if (!autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  };

  if (streamOutputLines.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      {/* Header bar */}
      <div className="flex items-center justify-between py-1 px-2.5 bg-mc-surface-2 rounded-t-lg border-b border-mc-border-0">
        <div className="text-[9px] text-mc-text-3 uppercase tracking-[0.5px] flex items-center gap-1.5">
          {isStreaming && (
            <span className="w-1.5 h-1.5 rounded-full bg-mc-green animate-pulse" />
          )}
          Live Output
          <span className="text-mc-text-3 ml-1">
            ({streamOutputLines.length} lines)
          </span>
        </div>

        <button
          onClick={toggleAutoScroll}
          className={`text-[9px] rounded py-[2px] px-1.5 cursor-pointer border ${
            autoScroll
              ? "text-mc-accent bg-mc-accent-muted border-mc-accent-border"
              : "text-mc-text-3 bg-transparent border-mc-border-1"
          }`}
        >
          {autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
        </button>
      </div>

      {/* Output container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="font-mono text-[10px] leading-relaxed text-mc-text-2 bg-mc-surface-0 border border-mc-border-0 border-t-0 rounded-b-lg py-2 px-2.5 text-left whitespace-pre-wrap break-words overflow-y-auto overflow-x-hidden"
        style={{ maxHeight }}
      >
        {streamOutputLines.map((line, index) => (
          <div key={index} className="flex min-h-[1.5em]">
            {showLineNumbers && (
              <span className="text-mc-text-3 mr-2 select-none min-w-[3ch] text-right">
                {index + 1}
              </span>
            )}
            <span className="flex-1">{line || " "}</span>
          </div>
        ))}

        {isStreaming && (
          <div className="inline-block w-1.5 h-3 bg-mc-accent ml-0.5 align-middle animate-[cc-blink_1s_step-end_infinite]" />
        )}
      </div>

      <style>
        {`
          @keyframes cc-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }
          @keyframes cc-blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0; }
          }
        `}
      </style>
    </div>
  );
}

export default StreamingOutput;
