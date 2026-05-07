import { useState } from "react";
import { useChatMessages, useChatInteract, IStep } from "@chainlit/react-client";
import { chatIntro, chatSuggestionTitle, workflowSuggestions } from "../config";
import { SettingsPanel } from "./SettingsPanel";
import { Header } from "./Header";
import { LeftPanel } from "./LeftPanel";

interface Props {
  onLogout: () => void;
}

function getMessages(messages: IStep[]): IStep[] {
  return messages.flatMap((m) => {
    const children = m.steps ? getMessages(m.steps) : [];
    if (m.type === "user_message" || m.type === "assistant_message") {
      return [m, ...children];
    }
    return children;
  });
}

function WelcomeScreen({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-6 gap-8">
      <div className="text-center space-y-2">
        <h1>{chatIntro}</h1>
        <p className="text-base-content">{chatSuggestionTitle}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
        {workflowSuggestions.map((suggestion) => (
          <button
            key={suggestion}
            className="card text-left px-4 py-3 bg-base-200 hover:bg-base-300 transition-colors cursor-pointer"
            onClick={() => onSelect(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Chat({ onLogout }: Props) {
  const [input, setInput] = useState("");
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const { messages } = useChatMessages();
  const { sendMessage } = useChatInteract();

  const flat = getMessages(messages);

  const handleSend = (content = input.trim()) => {
    if (!content) return;
    sendMessage({ name: "user", type: "user_message" as const, output: content }, []);
    setInput("");
  };

  return (
    <div className="flex flex-col h-screen bg-base-100 text-base-content">
      <Header onLogout={onLogout} onToggleSettings={() => setRightOpen((v) => !v)} />
      <div className="flex flex-1 overflow-hidden">
        <LeftPanel isOpen={leftOpen} onToggle={() => setLeftOpen((v) => !v)} />
        <main className="flex flex-col flex-1 w-full max-w-3xl mx-auto overflow-hidden">
          {flat.length === 0 ? (
            <WelcomeScreen onSelect={(text) => handleSend(text)} />
          ) : (
            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {flat.map((m) => (
                <div key={m.id} className={`flex ${m.type === "user_message" ? "justify-end" : "justify-start"}`}>
                  <span className={`px-4 py-2 rounded-xl max-w-xl text-sm whitespace-pre-wrap ${m.type === "user_message" ? "bg-base-300 text-base-content" : "bg-base-200 text-base-content"}`}>
                    {m.output}
                  </span>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2 p-4 border-t border-base-300">
            <input
              className="input input-bordered flex-1"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Message..."
              autoFocus
            />
            <button className="btn btn-primary" onClick={() => handleSend()}>
              Send
            </button>
          </div>
          <p className="text-center text-xs text-base-content/70">LLMs can make mistakes. Check important info.</p>
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
