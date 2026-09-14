import type { ReactNode } from "react";
import { MessageSquarePlus, PanelLeft } from "lucide-react";

interface Props {
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  /** Chat history, project list, etc. — kept as a slot so this stays a thin,
   * prop-only presentational shell. */
  children?: ReactNode;
}

export function LeftPanel({ isOpen, onToggle, onNewChat, children }: Props) {
  return (
    <aside
      className={`${isOpen ? "w-64" : "w-14"} bg-base-200 border-r border-base-300 transition-[width] duration-200 flex flex-col overflow-hidden`}
    >
      <div className={`flex flex-col gap-1 p-2 ${isOpen ? "" : "items-center"}`}>
        <button
          className="btn btn-ghost btn-sm btn-square"
          onClick={onToggle}
          aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          title={isOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          <PanelLeft size={18} />
        </button>
        <button
          className={`btn btn-sm ${
            isOpen
              ? "btn-accent w-full justify-start gap-2 px-3"
              : "btn-ghost btn-square"
          }`}
          onClick={onNewChat}
          aria-label="New chat"
          title="New chat"
        >
          <MessageSquarePlus size={18} className="shrink-0" />
          {isOpen && <span className="truncate">New chat</span>}
        </button>
      </div>
      {isOpen && <div className="flex-1 overflow-y-auto px-2 py-1">{children}</div>}
    </aside>
  );
}
