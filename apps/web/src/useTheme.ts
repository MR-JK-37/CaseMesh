import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

/** Manual override on top of the `prefers-color-scheme` default in theme.css. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("icm-theme") as Theme) ?? "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("icm-theme", theme);
    } catch {
      // per-viewer convenience only; ignore storage failures
    }
  }, [theme]);

  return [theme, setTheme];
}
