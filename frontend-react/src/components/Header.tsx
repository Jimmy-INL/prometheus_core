import { LogOut, Moon, Settings, Sun } from "lucide-react";
import { useTheme } from "../lib/useTheme";

interface Props {
  onLogout: () => void;
  onToggleSettings: () => void;
}

export function Header({ onLogout, onToggleSettings }: Props) {
  const [theme, setTheme] = useTheme();
  const logoSrc = theme === "light" ? "/logo_light.png" : "/logo_dark.png";
  const nextTheme = theme === "light" ? "dark" : "light";

  return (
    <div className="flex justify-between items-center gap-1 p-3 bg-base-300 border-b border-base-300">
      <img src={logoSrc} alt="Prometheus" className="h-8" />
      <div className="flex">
        <button className="btn btn-ghost btn-sm" onClick={onToggleSettings}>
          <Settings size={18} />
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setTheme(nextTheme)}
          aria-label={`Switch to ${nextTheme} theme`}
        >
          {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onLogout}>
          <LogOut size={18} />
        </button>
      </div>
    </div>
  );
}
