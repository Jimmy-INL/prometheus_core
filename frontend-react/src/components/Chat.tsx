import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { useChatMessages, useChatInteract, IStep } from "@chainlit/react-client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const { messages } = useChatMessages();
  const { sendMessage, stopTask } = useChatInteract();

  const flat = getMessages(messages);
  const lastMessage = flat[flat.length - 1];

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

  useEffect(() => {
    if (lastMessage?.type === "assistant_message") {
      setAwaitingResponse(false);
    }
  }, [lastMessage?.id, lastMessage?.type]);

  const handleSend = (content = input.trim()) => {
    if (!content) return;
    sendMessage({ name: "user", type: "user_message" as const, output: content }, []);
    setInput("");
    setAwaitingResponse(true);
  };

  const handleStop = () => {
    stopTask();
    setAwaitingResponse(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen bg-base-100 text-base-content">
      <Header onLogout={onLogout} onToggleSettings={() => setRightOpen((v) => !v)} />
      <div className="flex flex-1 overflow-hidden">
        <LeftPanel isOpen={leftOpen} onToggle={() => setLeftOpen((v) => !v)} />
        <main className="flex flex-col flex-1 w-full max-w-4xl mx-auto overflow-hidden">
          {flat.length === 0 ? (
            <WelcomeScreen onSelect={(text) => handleSend(text)} />
          ) : (
            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {flat.map((m) => (
                <div key={m.id} className={`flex ${m.type === "user_message" ? "justify-end" : "justify-start"}`}>
                  {m.type === "user_message" ? (
                    <span className="px-4 py-2 rounded-xl max-w-xl text-base whitespace-pre-wrap bg-base-300 text-base-content">
                      {m.output}
                    </span>
                  ) : (
                    <div className="w-full text-base text-base-content [&_p]:text-[length:inherit] [&_p]:leading-normal [&_span]:text-[length:inherit] [&_li]:text-[length:inherit] [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:bg-base-300 [&_pre]:bg-base-300 [&_pre]:p-2 [&_pre]:rounded [&_pre]:my-2 [&_pre]:overflow-x-auto [&_a]:underline">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.output}</ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}
              {awaitingResponse && lastMessage?.type === "user_message" && (
                <div className="flex justify-start" aria-live="polite" aria-label="Assistant is thinking">
                  <span className="loading loading-dots loading-md text-base-content" />
                </div>
              )}
            </div>
          )}
          <div className="px-4 pt-3 pb-2">
            <div className="relative flex items-end rounded-3xl border border-base-300 bg-base-200 shadow-sm focus-within:border-primary/60 focus-within:shadow-md transition-all">
              <textarea
                ref={textareaRef}
                className="flex-1 bg-transparent resize-none outline-none px-5 py-4 pr-14 text-base leading-6 placeholder:text-base-content/50 max-h-50"
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message..."
                autoFocus
              />
              <button
                className="btn btn-primary btn-circle btn-sm absolute bottom-2.5 right-2.5 disabled:opacity-40"
                onClick={() => (awaitingResponse ? handleStop() : handleSend())}
                disabled={!awaitingResponse && !input.trim()}
                aria-label={awaitingResponse ? "Stop response" : "Send message"}
              >
                {awaitingResponse ? <Square size={14} fill="currentColor" /> : <ArrowUp size={18} />}
              </button>
            </div>
          </div>
          <p className="text-center text-xs text-base-content/70 pb-2">LLMs can make mistakes. Check important info.</p>
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
