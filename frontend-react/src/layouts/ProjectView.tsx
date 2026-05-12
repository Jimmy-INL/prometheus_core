import { useState } from "react";
import { Chat } from "@/components/Chat";
import { SettingsPanel } from "@/components/SettingsPanel";
import { Header } from "@/components/Header";
import { LeftPanel } from "@/components/LeftPanel";

interface Props {
  onLogout: () => void;
}

export function ProjectView({ onLogout }: Props) {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  return (
    <div className="flex flex-col h-screen bg-base-100 text-base-content">
      <Header onLogout={onLogout} onToggleSettings={() => setRightOpen((v) => !v)} />
      <div className="flex flex-1 overflow-hidden">
        <LeftPanel isOpen={leftOpen} onToggle={() => setLeftOpen((v) => !v)} />
        <main className="flex flex-col flex-1 w-full max-w-3xl mx-auto overflow-hidden">
          <Chat onLogout={onLogout} />
        </main>
        <aside
          className={`${rightOpen ? "w-64 border-l bg-base-200 border-base-300" : "w-0"} transition-[width] duration-200 overflow-hidden flex flex-col`}
        >
          <SettingsPanel onClose={() => setRightOpen(false)} />
        </aside>
      </div>
    </div>
  );
}
