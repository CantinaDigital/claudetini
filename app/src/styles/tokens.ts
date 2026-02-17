// Design tokens - "Mission Control" theme
// Bloomberg terminal meets Linear meets Raycast

export const tokens = {
  // Surfaces
  bg: "#0c0c0f",
  surface0: "#111116",
  surface1: "#18181f",
  surface2: "#1f1f28",
  surface3: "#262630",

  // Borders
  border0: "rgba(255,255,255,0.04)",
  border1: "rgba(255,255,255,0.07)",
  border2: "rgba(255,255,255,0.12)",

  // Text
  text0: "#f0f0f5",
  text1: "#c8c8d4",
  text2: "#8b8b9e",
  text3: "#5c5c6e",

  // Accent (softer purple)
  accent: "#8b7cf6",
  accentMuted: "rgba(139,124,246,0.12)",
  accentBorder: "rgba(139,124,246,0.25)",

  // Status colors
  green: "#34d399",
  greenMuted: "rgba(52,211,153,0.1)",
  greenBorder: "rgba(52,211,153,0.2)",

  red: "#f87171",
  redMuted: "rgba(248,113,113,0.08)",
  redBorder: "rgba(248,113,113,0.18)",

  amber: "#fbbf24",
  amberMuted: "rgba(251,191,36,0.08)",
  amberBorder: "rgba(251,191,36,0.18)",

  // Cyan (for branch strategy, etc.)
  cyan: "#22d3ee",
  cyanMuted: "rgba(34,211,238,0.12)",
  cyanBorder: "rgba(34,211,238,0.25)",

  // Gradient endpoints (used in progress bars, badges)
  accentDark: "#6d5bd0",
  greenLight: "#2dd4a0",
} as const;

// Typography
export const fonts = {
  mono: "'IBM Plex Mono', 'JetBrains Mono', monospace",
  sans: "'Satoshi', 'DM Sans', -apple-system, sans-serif",
} as const;

// Shorthand for use in inline styles
export const t = tokens;
export const mono = fonts.mono;
export const sans = fonts.sans;
