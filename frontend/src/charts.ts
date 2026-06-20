import type { CSSProperties } from "react";

// Sentiment colors are the only color in the UI (reserved for data). Everything else is ink.
export const POS = "#15803d";
export const NEU = "#a1a1aa";
export const NEG = "#b91c1c";

export interface ChartTheme {
  tick: string;
  grid: string;
  bar: string; // ink fill for non-sentiment series (keyword bar, trend line)
  tooltipContentStyle: CSSProperties;
  tooltipItemStyle: CSSProperties;
  tooltipCursor: { fill: string };
}

// Recharts ignores the `dark` class, so feed it explicit colors per theme.
export function chartTheme(isDark: boolean): ChartTheme {
  return isDark
    ? {
        tick: "#a1a1aa", // zinc-400
        grid: "#27272a", // zinc-800
        bar: "#d4d4d8", // zinc-300 (ink on dark)
        tooltipContentStyle: {
          background: "#18181b",
          border: "1px solid #3f3f46",
          borderRadius: 12,
          color: "#fafafa",
          fontSize: 12,
          boxShadow: "0 8px 24px -8px rgba(0,0,0,.6)",
        },
        tooltipItemStyle: { color: "#fafafa" },
        tooltipCursor: { fill: "rgba(255,255,255,0.05)" },
      }
    : {
        tick: "#71717a", // zinc-500
        grid: "#e4e4e7", // zinc-200
        bar: "#3f3f46", // zinc-700 (ink on light)
        tooltipContentStyle: {
          background: "#ffffff",
          border: "1px solid #e4e4e7",
          borderRadius: 12,
          color: "#18181b",
          fontSize: 12,
          boxShadow: "0 8px 24px -8px rgba(0,0,0,.15)",
        },
        tooltipItemStyle: { color: "#18181b" },
        tooltipCursor: { fill: "rgba(0,0,0,0.04)" },
      };
}
