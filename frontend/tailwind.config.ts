import type { Config } from "tailwindcss";

// Design tokens for the CardFlow operational dashboard.
// Palette: soft neutral grayscale + status-only accents (Linear/Attio/Vercel-inspired).
// Spacing follows an 8px rhythm; radii and shadows are intentionally restrained
// so borders — not elevation — carry visual hierarchy.
export default {
  darkMode: "class",
  content: ["./index.html", "./**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      colors: {
        background: "#F7F7F5",
        surface: "#FFFFFF",
        border: "#ECECEC",

        primary: {
          DEFAULT: "#161616",
          foreground: "#FFFFFF",
        },
        "muted-foreground": "#71717A",
        muted: "#F1F1EE",

        // Status-only accents. Never decorative — each pair communicates
        // one operational state (processing / info / warning / success / error).
        "accent-lavender": "#EEEEFC",
        "accent-lavender-foreground": "#5457C6",
        "accent-lavender-solid": "#6366F1",

        "accent-blue": "#EAF1FE",
        "accent-blue-foreground": "#2A63C7",
        "accent-blue-solid": "#3B82F6",

        "accent-peach": "#FCF1E4",
        "accent-peach-foreground": "#B4702E",
        "accent-peach-solid": "#F0973D",

        "accent-mint": "#E8F6EE",
        "accent-mint-foreground": "#227A4C",
        "accent-mint-solid": "#22C55E",

        "accent-rose": "#FBEAEA",
        "accent-rose-foreground": "#BE3B3B",
        "accent-rose-solid": "#EF4444",
      },
      borderRadius: {
        // Cards/panels: 12px. Buttons/inputs/pills: 10px. Keep existing
        // Tailwind scale (sm/md/lg/full…) intact for anything ad hoc.
        xl: "12px",
        lg: "10px",
      },
      fontSize: {
        "page-title": ["28px", { lineHeight: "34px", fontWeight: "600", letterSpacing: "-0.01em" }],
        section: ["14px", { lineHeight: "20px", fontWeight: "600" }],
        "card-title": ["13px", { lineHeight: "18px", fontWeight: "600" }],
        body: ["13px", { lineHeight: "20px", fontWeight: "400" }],
        caption: ["11px", { lineHeight: "16px", fontWeight: "500" }],
      },
      boxShadow: {
        // Minimal — borders do the heavy lifting; shadow only adds
        // separation for floating/overlay surfaces.
        soft: "0 1px 2px 0 rgba(22, 22, 22, 0.03)",
        float: "0 4px 12px -2px rgba(22, 22, 22, 0.07)",
        "float-lg": "0 16px 40px -8px rgba(22, 22, 22, 0.14)",
      },
      spacing: {
        4.5: "1.125rem",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "lift-in": {
          from: { opacity: "0", transform: "translateY(6px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "dialog-lift-in": {
          from: { opacity: "0", transform: "translate(-50%, -46%) scale(0.98)" },
          to: { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "lift-in": "lift-in 200ms ease-out",
        "dialog-lift-in": "dialog-lift-in 180ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
