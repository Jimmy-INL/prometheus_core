import { PanelLeft } from "lucide-react";

interface Props {
  isOpen: boolean;
  onToggle: () => void;
}

export function LeftPanel({ isOpen, onToggle }: Props) {
  return (
    <aside
      className={`${isOpen ? "w-64" : "w-14"} bg-base-200 border-r border-base-300 transition-[width] duration-200 flex flex-col overflow-hidden`}
    >
      <div className="flex items-center p-2 min-h-11">
        <button className="btn btn-ghost btn-sm" onClick={onToggle}>
          <PanelLeft size={18} />
        </button>
      </div>
      {isOpen && (
        <div className="px-3 py-2 text-sm text-base-content/60">
          {/* Chat history, project list, etc. go here */}
        </div>
      )}
    </aside>
  );
}
