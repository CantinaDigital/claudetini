import { useState, useRef, useEffect } from "react";
import { Icons } from "./Icons";

interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  small?: boolean;
  disabled?: boolean;
  className?: string;
}

export function Select({
  value,
  onChange,
  options,
  small = false,
  disabled = false,
  className = "",
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen]);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-1.5 rounded-md bg-mc-surface-2 border border-mc-border-1 font-mono font-medium cursor-pointer outline-none transition-[border-color,background] duration-150 text-left ${
          small ? "py-1 pl-2.5 pr-6 text-[10.5px] min-w-[60px]" : "py-1.5 pl-3 pr-7 text-xs min-w-[80px]"
        } ${disabled ? "text-mc-text-3 cursor-not-allowed opacity-60" : "text-mc-text-1"}`}
      >
        {selectedOption?.icon && <span className="flex">{selectedOption.icon}</span>}
        <span className="flex-1">{selectedOption?.label || "Select..."}</span>
        <span
          className={`absolute top-1/2 -translate-y-1/2 text-mc-text-3 flex transition-transform duration-150 ${
            small ? "right-1.5" : "right-2"
          } ${isOpen ? "rotate-180" : ""}`}
        >
          <Icons.chevDown size={10} />
        </span>
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute top-[calc(100%+4px)] left-0 min-w-full bg-mc-surface-2 border border-mc-border-1 rounded-lg shadow-[0_8px_24px_rgba(0,0,0,0.4),0_2px_8px_rgba(0,0,0,0.3)] z-[1000] py-1 animate-fade-in">
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => handleSelect(option.value)}
                className={`flex items-center gap-2 w-full py-2 px-3 bg-transparent border-none text-xs font-mono cursor-pointer text-left transition-[background,color] duration-100 hover:bg-mc-surface-3 hover:text-mc-text-0 ${
                  isSelected ? "text-mc-text-0 font-semibold" : "text-mc-text-2 font-normal"
                }`}
              >
                {/* Checkmark for selected */}
                <span className={`w-3.5 flex shrink-0 ${isSelected ? "text-mc-accent" : "text-transparent"}`}>
                  {isSelected && <Icons.check size={12} />}
                </span>
                {option.icon && <span className="flex">{option.icon}</span>}
                <span className="flex-1 whitespace-nowrap">{option.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
