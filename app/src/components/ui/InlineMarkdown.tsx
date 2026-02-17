interface InlineMarkdownProps {
  children: string;
  className?: string;
}

/**
 * Renders basic inline markdown: **bold**, *italic*, `code`
 * Used for displaying content parsed from .md files
 */
export function InlineMarkdown({ children, className }: InlineMarkdownProps) {
  const parts = parseInlineMarkdown(children);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        switch (part.type) {
          case "bold":
            return (
              <strong key={i} className="font-bold">
                {part.content}
              </strong>
            );
          case "italic":
            return (
              <em key={i} className="italic">
                {part.content}
              </em>
            );
          case "code":
            return (
              <code
                key={i}
                className="font-mono text-[0.9em] px-[5px] py-px rounded bg-mc-surface-3 text-mc-text-1"
              >
                {part.content}
              </code>
            );
          default:
            return <span key={i}>{part.content}</span>;
        }
      })}
    </span>
  );
}

interface TextPart {
  type: "text" | "bold" | "italic" | "code";
  content: string;
}

function parseInlineMarkdown(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let remaining = text;

  // Regex patterns for inline markdown
  // Order matters: bold (**) before italic (*) to avoid conflicts
  const patterns: { regex: RegExp; type: "bold" | "italic" | "code" }[] = [
    { regex: /\*\*(.+?)\*\*/, type: "bold" },      // **bold**
    { regex: /__(.+?)__/, type: "bold" },          // __bold__
    { regex: /\*(.+?)\*/, type: "italic" },        // *italic*
    { regex: /_(.+?)_/, type: "italic" },          // _italic_
    { regex: /`(.+?)`/, type: "code" },            // `code`
  ];

  while (remaining.length > 0) {
    let earliestMatch: { index: number; length: number; content: string; type: "bold" | "italic" | "code" } | null = null;

    // Find the earliest match among all patterns
    for (const { regex, type } of patterns) {
      const match = remaining.match(regex);
      if (match && match.index !== undefined) {
        if (!earliestMatch || match.index < earliestMatch.index) {
          earliestMatch = {
            index: match.index,
            length: match[0].length,
            content: match[1],
            type,
          };
        }
      }
    }

    if (earliestMatch) {
      // Add text before the match
      if (earliestMatch.index > 0) {
        parts.push({ type: "text", content: remaining.slice(0, earliestMatch.index) });
      }

      // Add the matched formatted text
      parts.push({ type: earliestMatch.type, content: earliestMatch.content });

      // Continue with remaining text
      remaining = remaining.slice(earliestMatch.index + earliestMatch.length);
    } else {
      // No more matches, add remaining text
      parts.push({ type: "text", content: remaining });
      break;
    }
  }

  return parts;
}
