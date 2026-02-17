/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        mc: {
          bg: "#0c0c0f",
          surface: {
            0: "#111116",
            1: "#18181f",
            2: "#1f1f28",
            3: "#262630",
          },
          border: {
            0: "rgba(255,255,255,0.04)",
            1: "rgba(255,255,255,0.07)",
            2: "rgba(255,255,255,0.12)",
          },
          text: {
            0: "#f0f0f5",
            1: "#c8c8d4",
            2: "#8b8b9e",
            3: "#5c5c6e",
          },
          accent: {
            DEFAULT: "#8b7cf6",
            dark: "#6d5bd0",
            muted: "rgba(139,124,246,0.12)",
            border: "rgba(139,124,246,0.25)",
          },
          green: {
            DEFAULT: "#34d399",
            light: "#2dd4a0",
            muted: "rgba(52,211,153,0.1)",
            border: "rgba(52,211,153,0.2)",
          },
          red: {
            DEFAULT: "#f87171",
            muted: "rgba(248,113,113,0.08)",
            border: "rgba(248,113,113,0.18)",
          },
          amber: {
            DEFAULT: "#fbbf24",
            muted: "rgba(251,191,36,0.08)",
            border: "rgba(251,191,36,0.18)",
          },
          cyan: {
            DEFAULT: "#22d3ee",
            muted: "rgba(34,211,238,0.12)",
            border: "rgba(34,211,238,0.25)",
          },
        },
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "'JetBrains Mono'", "monospace"],
        sans: ["'Satoshi'", "'DM Sans'", "-apple-system", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease",
        "fade-in-fast": "fadeIn 0.2s ease",
        "fade-in-fastest": "fadeIn 0.15s ease",
        "slide-up": "slideUp 0.2s ease",
        "slide-in": "slideIn 0.25s ease",
        "scale-in": "scaleIn 0.2s ease-out",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 1.5s infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(20px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
    },
  },
  plugins: [],
};
