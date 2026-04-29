import type { Config } from "tailwindcss";

/**
 * Ultimate Trader theme tokens.
 *
 * Color semantics from docs/architecture/UI_VISUAL_DIRECTION.md:
 *   green  = healthy / profit / connected
 *   red    = danger / live / blocked / failure
 *   amber  = warning / stale / manual attention
 *   cyan   = neutral platform action
 *   purple = AI only, never dominant
 *
 * All colors resolve through CSS variables defined in src/styles/theme.css
 * so dark/light themes swap by toggling a [data-theme] attribute on the
 * document root.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="light"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      colors: {
        bg: {
          DEFAULT: "rgb(var(--ut-bg) / <alpha-value>)",
          subtle: "rgb(var(--ut-bg-subtle) / <alpha-value>)",
          raised: "rgb(var(--ut-bg-raised) / <alpha-value>)",
          inset: "rgb(var(--ut-bg-inset) / <alpha-value>)",
        },
        fg: {
          DEFAULT: "rgb(var(--ut-fg) / <alpha-value>)",
          muted: "rgb(var(--ut-fg-muted) / <alpha-value>)",
          subtle: "rgb(var(--ut-fg-subtle) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--ut-border) / <alpha-value>)",
          strong: "rgb(var(--ut-border-strong) / <alpha-value>)",
        },
        ok: {
          DEFAULT: "rgb(var(--ut-ok) / <alpha-value>)",
          subtle: "rgb(var(--ut-ok-subtle) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "rgb(var(--ut-danger) / <alpha-value>)",
          subtle: "rgb(var(--ut-danger-subtle) / <alpha-value>)",
        },
        warn: {
          DEFAULT: "rgb(var(--ut-warn) / <alpha-value>)",
          subtle: "rgb(var(--ut-warn-subtle) / <alpha-value>)",
        },
        info: {
          DEFAULT: "rgb(var(--ut-info) / <alpha-value>)",
          subtle: "rgb(var(--ut-info-subtle) / <alpha-value>)",
        },
        ai: {
          DEFAULT: "rgb(var(--ut-ai) / <alpha-value>)",
          subtle: "rgb(var(--ut-ai-subtle) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--ut-accent) / <alpha-value>)",
        },
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
      },
      boxShadow: {
        card: "0 1px 0 0 rgb(var(--ut-border) / 0.6), 0 1px 2px 0 rgb(0 0 0 / 0.18)",
        raised:
          "0 4px 12px -2px rgb(0 0 0 / 0.30), 0 2px 4px -2px rgb(0 0 0 / 0.18)",
      },
      keyframes: {
        "ut-pulse": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.55", transform: "scale(0.92)" },
        },
        "ut-flash": {
          "0%": { opacity: "0", transform: "scale(0.6)" },
          "30%": { opacity: "1", transform: "scale(1.05)" },
          "100%": { opacity: "0", transform: "scale(1.4)" },
        },
        "ut-slide-in-right": {
          "0%": { transform: "translateX(100%)" },
          "100%": { transform: "translateX(0)" },
        },
        "ut-slide-out-right": {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "ut-pulse": "ut-pulse 1.4s ease-in-out infinite",
        "ut-flash": "ut-flash 1s ease-out 1",
        "ut-slide-in-right": "ut-slide-in-right 200ms ease-out",
        "ut-slide-out-right": "ut-slide-out-right 200ms ease-in",
      },
    },
  },
  plugins: [],
};

export default config;
