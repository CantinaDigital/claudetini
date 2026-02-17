import { useCallback, useRef } from "react";

interface TabBarProps {
  tabs: string[];
  activeTab: number;
  onTabChange: (index: number) => void;
}

export function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      let next = activeTab;
      if (event.key === "ArrowRight") {
        next = (activeTab + 1) % tabs.length;
      } else if (event.key === "ArrowLeft") {
        next = (activeTab - 1 + tabs.length) % tabs.length;
      } else if (event.key === "Home") {
        next = 0;
      } else if (event.key === "End") {
        next = tabs.length - 1;
      } else {
        return;
      }
      event.preventDefault();
      onTabChange(next);
      tabRefs.current[next]?.focus();
    },
    [activeTab, tabs.length, onTabChange],
  );

  return (
    <nav
      role="tablist"
      className="flex gap-0 border-b border-mc-border-0 px-6 bg-mc-surface-0 items-center"
    >
      {tabs.map((name, i) => (
        <button
          key={name}
          ref={(el) => { tabRefs.current[i] = el; }}
          role="tab"
          aria-selected={activeTab === i}
          tabIndex={activeTab === i ? 0 : -1}
          onClick={() => onTabChange(i)}
          onKeyDown={handleKeyDown}
          className={`py-[13px] px-[18px] text-[12.5px] bg-transparent border-none cursor-pointer font-sans transition-all duration-150 -mb-px outline-none border-b-2 ${
            activeTab === i
              ? "font-semibold text-mc-text-0 border-b-mc-accent"
              : "font-normal text-mc-text-3 border-b-transparent"
          }`}
        >
          {name}
        </button>
      ))}
    </nav>
  );
}
