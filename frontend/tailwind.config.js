/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#111827",
          foreground: "#FFFFFF",
        },
        background: "#F7F8FA",
        surface: "#FFFFFF",
        border: {
          DEFAULT: "#E7E8EC",
        },
        muted: {
          DEFAULT: "#F1F2F5",
          foreground: "#6B7280",
        },
        accent: {
          lavender: { DEFAULT: "#EDE9FE", foreground: "#6D28D9", solid: "#A78BFA" },
          blue: { DEFAULT: "#DBEAFE", foreground: "#1D4ED8", solid: "#60A5FA" },
          peach: { DEFAULT: "#FFE8D9", foreground: "#C2410C", solid: "#FDBA88" },
          mint: { DEFAULT: "#DCFCE7", foreground: "#15803D", solid: "#6EE7B7" },
          rose: { DEFAULT: "#FFE4E9", foreground: "#BE123C", solid: "#FB7185" },
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        display: ["32px", { lineHeight: "40px", fontWeight: "700", letterSpacing: "-0.02em" }],
        "page-title": ["28px", { lineHeight: "36px", fontWeight: "700", letterSpacing: "-0.01em" }],
        section: ["20px", { lineHeight: "28px", fontWeight: "600" }],
        "card-title": ["16px", { lineHeight: "24px", fontWeight: "600" }],
        body: ["14px", { lineHeight: "22px", fontWeight: "400" }],
        caption: ["12px", { lineHeight: "18px", fontWeight: "500" }],
      },
      borderRadius: {
        xl: "18px",
        "2xl": "22px",
        "3xl": "28px",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(17, 24, 39, 0.04), 0 8px 24px -8px rgba(17, 24, 39, 0.08)",
        float: "0 12px 32px -12px rgba(17, 24, 39, 0.18)",
        "float-lg": "0 24px 48px -16px rgba(17, 24, 39, 0.22)",
      },
      spacing: {
        18: "72px",
      },
      keyframes: {
        "fade-in": { from: { opacity: 0 }, to: { opacity: 1 } },
        "fade-in-up": {
          from: { opacity: 0, transform: "translateY(6px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        "lift-in": {
          from: { opacity: 0, transform: "translateY(4px) scale(0.98)" },
          to: { opacity: 1, transform: "translateY(0) scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "fade-in-up": "fade-in-up 200ms ease-out",
        "lift-in": "lift-in 180ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
