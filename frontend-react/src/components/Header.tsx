import { LogOut, Settings } from "lucide-react";
import { useTheme } from "../lib/useTheme";

interface Props {
  onLogout: () => void;
  onToggleSettings: () => void;
}

export function Header({ onLogout, onToggleSettings }: Props) {
  const theme = useTheme();
  const logoSrc = theme === "light" ? "/logo_light.png" : "/logo_dark.png";

  return (
    <div className="flex justify-between items-center gap-1 p-3 bg-base-300 border-b border-base-300">
      <img src={logoSrc} alt="Prometheus" className="h-8" />
      <div className="flex gap-1">
        <button className="btn btn-ghost btn-sm" onClick={onToggleSettings}>
          <Settings size={18} />
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onLogout}>
          <LogOut size={18} />
        </button>
      </div>
    </div>
  );
}
