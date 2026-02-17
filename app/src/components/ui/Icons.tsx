// SVG Icons used throughout the app

interface IconProps {
  size?: number;
  color?: string;
}

export const Icons = {
  play: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path d="M3 1.5L10 6L3 10.5V1.5Z" fill={color} />
    </svg>
  ),

  check: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path
        d="M2.5 6L5 8.5L9.5 3.5"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),

  chevDown: ({ size = 10, color = "currentColor", open = false }: IconProps & { open?: boolean } = {}) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 10 10"
      fill="none"
      className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`}
    >
      <path
        d="M2.5 3.75L5 6.25L7.5 3.75"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),

  edit: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path
        d="M8.5 1.5L10.5 3.5L4 10H2V8L8.5 1.5Z"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),

  x: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path d="M3 3L9 9M9 3L3 9" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),

  alert: ({ size = 12, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M7 1L13 12H1L7 1Z" stroke={color} strokeWidth="1.2" fill="none" />
      <line x1="7" y1="5.5" x2="7" y2="8.5" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="7" cy="10" r="0.6" fill={color} />
    </svg>
  ),

  branch: ({ size = 12, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" style={{ color }}>
      <circle cx="4" cy="3.5" r="1.3" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="4" cy="10.5" r="1.3" stroke="currentColor" strokeWidth="1.1" />
      <circle cx="10" cy="5.5" r="1.3" stroke="currentColor" strokeWidth="1.1" />
      <path d="M4 4.8V9.2" stroke="currentColor" strokeWidth="1.1" />
      <path d="M4 4.8C4 4.8 4 6.5 6 6.5H8.7" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  ),

  refresh: ({ size = 12, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path
        d="M2 7a5 5 0 0 1 8.54-3.54M12 7a5 5 0 0 1-8.54 3.54"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <path d="M2 3v4h4M12 11V7H8" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  retry: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path
        d="M1 6a5 5 0 019-2M11 6a5 5 0 01-9 2"
        stroke={color}
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <path
        d="M10 1v3h-3M2 11V8h3"
        stroke={color}
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),

  lock: ({ size = 12, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <rect x="2" y="5" width="8" height="6" rx="1" stroke={color} strokeWidth="1.1" />
      <path d="M4 5V3.5a2 2 0 014 0V5" stroke={color} strokeWidth="1.1" />
      <circle cx="6" cy="8" r="1" fill={color} />
    </svg>
  ),

  folder: ({ size = 13, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <path d="M1.5 3.5V11a1 1 0 001 1h9a1 1 0 001-1V5.5a1 1 0 00-1-1H7L5.5 3H2.5a1 1 0 00-1 .5z" stroke={color} strokeWidth="1.1" />
    </svg>
  ),

  bolt: ({ size = 11, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path d="M6.5 1L3 7h3l-.5 4L9 5H6l.5-4z" fill={color} />
    </svg>
  ),

  arrow: ({ size = 10, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none">
      <path d="M2 6h8M7 3l3 3-3 3" stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  search: ({ size = 12, color = "currentColor" }: IconProps = {}) => (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <circle cx="6" cy="6" r="4.5" stroke={color} strokeWidth="1.3" />
      <path d="M9.5 9.5L13 13" stroke={color} strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
};
