interface TagProps {
  children: React.ReactNode;
  color?: string;
  bg?: string;
}

export function Tag({ children, color, bg }: TagProps) {
  return (
    <span
      className="mc-tag bg-mc-surface-2 text-mc-text-3"
      style={color || bg ? { ...(color ? { color } : {}), ...(bg ? { background: bg } : {}) } : undefined}
    >
      {children}
    </span>
  );
}
