import type { Config } from "tailwindcss";

// Design tokens for the CardFlow operational dashboard.
// Palette: soft neutral grayscale + status-only accents (Linear/Attio/Vercel-inspired).
// Spacing follows an 8px rhythm; radii and shadows are intentionally restrained
// so borders — not elevation — carry visual hierarchy.
//
// Colors are driven by CSS variables defined in index.css so that dark mode
// works by toggling the `.dark` class on <html> — no `dark:` prefixes needed.
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
        background: "var(--color-background)",
        surface: "var(--color-surface)",
        border: "var(--color-border)",

        primary: "var(--color-primary)",
        "primary-foreground": "var(--color-primary-foreground)",
        "muted-foreground": "var(--color-muted-foreground)",
        muted: "var(--color-muted)",

        // Dedicated token for primary action buttons (avoids conflation with
        // the primary text colour which changes meaning in dark mode).
        interactive: "var(--color-interactive)",
        "interactive-text": "var(--color-interactive-text)",

        // Status-only accents — each pair communicates one operational state.
        "accent-lavender": "var(--color-accent-lavender)",
        "accent-lavender-foreground": "var(--color-accent-lavender-foreground)",
        "accent-lavender-solid": "var(--color-accent-lavender-solid)",

        "accent-blue": "var(--color-accent-blue)",
        "accent-blue-foreground": "var(--color-accent-blue-foreground)",
        "accent-blue-solid": "var(--color-accent-blue-solid)",

        "accent-peach": "var(--color-accent-peach)",
        "accent-peach-foreground": "var(--color-accent-peach-foreground)",
        "accent-peach-solid": "var(--color-accent-peach-solid)",

        "accent-mint": "var(--color-accent-mint)",
        "accent-mint-foreground": "var(--color-accent-mint-foreground)",
        "accent-mint-solid": "var(--color-accent-mint-solid)",

        "accent-rose": "var(--color-accent-rose)",
        "accent-rose-foreground": "var(--color-accent-rose-foreground)",
        "accent-rose-solid": "var(--color-accent-rose-solid)",
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
        soft: "0 1px 2px 0 rgba(90, 80, 160, 0.05)",
        float: "0 4px 12px -2px rgba(90, 80, 160, 0.08)",
        "float-lg": "0 16px 40px -8px rgba(90, 80, 160, 0.14)",
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
