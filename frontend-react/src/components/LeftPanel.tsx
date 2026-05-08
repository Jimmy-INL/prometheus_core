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
      <div className="p-2">
        <button className="btn btn-ghost btn-sm" onClick={onToggle}>
          <PanelLeft size={18} />
        </button>
      </div>
      {isOpen && (
        <div className="px-3 py-2 text-sm text-base-content/60">Left panel</div>
      )}
    </aside>
  );
}
