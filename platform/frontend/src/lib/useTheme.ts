import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

function getSystemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function readTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "light" ? "light" : attr === "dark" ? "dark" : getSystemTheme();
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(() => {
    const initial = readTheme();
    if (!document.documentElement.hasAttribute("data-theme")) {
      applyTheme(initial);
    }
    return initial;
  });

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeState(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next);
  }, []);

  return [theme, setTheme];
}
