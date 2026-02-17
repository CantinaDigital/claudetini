import { useRef } from "react";
import { Icons } from "../ui/Icons";

interface AskInputProps {
  askPrompt: string;
  onAskPromptChange: (value: string) => void;
  dispatchMode: string;
  onDispatch: () => void;
}

const MODE_LABELS: Record<string, string> = {
  standard: "std",
  "with-review": "--agents",
  "full-pipeline": "pipeline",
  blitz: "blitz",
};

export function AskInput({
  askPrompt,
  onAskPromptChange,
  dispatchMode,
  onDispatch,
}: AskInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hasText = askPrompt.trim().length > 0;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && hasText) {
      e.preventDefault();
      onDispatch();
    }
  };

  return (
    <div
      className={`flex items-center gap-2.5 py-2.5 px-4 rounded-[10px] bg-mc-surface-1 border transition-[border-color] duration-150 ${
        hasText ? "border-mc-accent-border" : "border-mc-border-0"
      }`}
    >
      {/* Arrow prompt indicator */}
      <span className="text-[13px] text-mc-text-3 shrink-0">{"\u2192"}</span>

      {/* Text input */}
      <input
        ref={inputRef}
        type="text"
        value={askPrompt}
        onChange={(e) => onAskPromptChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Describe a task to dispatch to terminal..."
        className="flex-1 bg-transparent border-none outline-none text-[12.5px] font-sans text-mc-text-0 leading-[1.4]"
      />

      {/* Mode badge */}
      <span className="text-[10px] font-mono text-mc-text-3 shrink-0">
        {MODE_LABELS[dispatchMode] || dispatchMode}
      </span>

      {/* Dispatch button */}
      <button
        onClick={onDispatch}
        disabled={!hasText}
        className={`inline-flex items-center gap-[5px] text-[11px] font-semibold font-sans text-white bg-mc-accent border-none rounded-md py-1 px-2.5 shrink-0 transition-opacity duration-150 ${
          hasText ? "cursor-pointer opacity-100" : "cursor-default opacity-40"
        }`}
      >
        <Icons.play size={10} color="#fff" /> Dispatch
      </button>
    </div>
  );
}
