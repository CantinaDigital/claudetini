/**
 * Renders text with diff-aware formatting.
 * Lines starting with `+` are green, `-` are red, `@@` are cyan headers.
 * `diff --git` lines are shown as muted section separators.
 * Non-diff text is passed through as-is.
 */

const DIFF_INDICATORS = /^(diff --git |@@|\+\+\+ |\-\-\- )/;

/** Returns true when the text looks like a unified diff. */
export function looksLikeDiff(text: string): boolean {
  const lines = text.split("\n");
  let diffMarkers = 0;
  for (const line of lines) {
    if (DIFF_INDICATORS.test(line)) diffMarkers++;
    if (diffMarkers >= 2) return true;
  }
  return false;
}

interface DiffBlockProps {
  text: string;
  maxHeight?: number;
}

export function DiffBlock({ text, maxHeight = 300 }: DiffBlockProps) {
  const lines = text.split("\n");

  return (
    <pre
      className="font-mono text-[10.5px] leading-[1.55] m-0 bg-mc-bg border border-mc-border-0 rounded-lg p-3 overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words"
      style={{ maxHeight }}
    >
      {lines.map((line, i) => {
        let cls = "text-mc-text-2";

        if (line.startsWith("diff --git")) {
          cls = "text-mc-text-3 font-bold";
        } else if (line.startsWith("@@")) {
          cls = "text-mc-cyan";
        } else if (line.startsWith("+++") || line.startsWith("---")) {
          cls = "text-mc-text-3";
        } else if (line.startsWith("+")) {
          cls = "text-mc-green";
        } else if (line.startsWith("-")) {
          cls = "text-mc-red";
        }

        return (
          <div key={i} className={cls}>
            {line || "\u00A0"}
          </div>
        );
      })}
    </pre>
  );
}
