interface ToggleProps {
  on: boolean;
  locked?: boolean;
  onClick?: () => void;
}

export function Toggle({ on, locked, onClick }: ToggleProps) {
  return (
    <div
      onClick={locked ? undefined : onClick}
      className={`w-[38px] h-5 rounded-[10px] relative shrink-0 transition-all duration-200 border ${
        on ? "bg-mc-accent border-mc-accent-border" : "bg-mc-surface-3 border-mc-border-1"
      } ${locked ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
    >
      <div
        className={`w-3.5 h-3.5 rounded-full absolute top-[2px] transition-all duration-200 ${
          on ? "bg-white left-[21px]" : "bg-mc-text-3 left-[3px]"
        }`}
      />
    </div>
  );
}
