import { useCallback, useState } from "react";

export type Theme = "light" | "dark";
const STORAGE_KEY = "voc-theme";

// Single source of truth lives on <html>.classList (set pre-paint by the inline script in
// index.html). Use ONE instance of this hook (in App) and pass `isDark` down, so toggling
// re-renders every consumer (charts) — independent instances would not stay in sync.
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore unavailable storage */
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
  }, [setTheme]);

  return { theme, isDark: theme === "dark", toggle };
}
