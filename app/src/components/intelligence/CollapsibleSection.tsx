import { useState, useRef, useEffect, type ReactNode } from "react";
import { Icons } from "../ui/Icons";

interface CollapsibleSectionProps {
  title: string;
  icon: ReactNode;
  subtitle?: string;
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function CollapsibleSection({
  title,
  icon,
  subtitle,
  badge,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState<number | undefined>(
    defaultOpen ? undefined : 0,
  );

  useEffect(() => {
    if (!contentRef.current) return;
    if (open) {
      setContentHeight(contentRef.current.scrollHeight);
      // After transition, switch to auto so dynamic content works
      const timer = setTimeout(() => setContentHeight(undefined), 200);
      return () => clearTimeout(timer);
    } else {
      // Set explicit height first so transition can animate from it
      setContentHeight(contentRef.current.scrollHeight);
      // Force reflow then collapse
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setContentHeight(0));
      });
    }
  }, [open]);

  return (
    <div className="bg-mc-surface-1 border border-mc-border-0 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex items-center w-full px-4 py-3 gap-2.5 cursor-pointer select-none hover:bg-mc-surface-2 transition-colors duration-150"
      >
        <span className="flex-shrink-0 text-mc-text-2">{icon}</span>
        <span className="flex-1 flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-mc-text-0 truncate">
            {title}
          </span>
          {subtitle && (
            <span className="text-[10px] text-mc-text-3 font-mono truncate">
              {subtitle}
            </span>
          )}
        </span>
        {badge && <span className="flex-shrink-0">{badge}</span>}
        <span className="flex-shrink-0 text-mc-text-3">
          {Icons.chevDown({ size: 10, open })}
        </span>
      </button>
      <div
        ref={contentRef}
        style={{
          height: contentHeight !== undefined ? contentHeight : "auto",
          overflow: "hidden",
          transition: "height 200ms ease",
        }}
        aria-hidden={!open}
      >
        <div className="border-t border-mc-border-0">{children}</div>
      </div>
    </div>
  );
}
