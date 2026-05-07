import { useEffect, useState } from "react";

function readTheme(): string {
  return document.documentElement.getAttribute("data-theme") ?? "dark";
}

export function useTheme(): string {
  const [theme, setTheme] = useState(readTheme);

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return theme;
}
