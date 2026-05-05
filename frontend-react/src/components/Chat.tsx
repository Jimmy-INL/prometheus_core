import { useState } from "react";
import { useChatMessages, useChatInteract, IStep } from "@chainlit/react-client";
import { chatIntro, chatSuggestionTitle, workflowSuggestions } from "../config";
import { LogOut } from "lucide-react";

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
        <h1 className="text-2xl font-semibold text-gray-100">{chatIntro}</h1>
        <p className="text-gray-400 text-sm">{chatSuggestionTitle}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
        {workflowSuggestions.map((suggestion) => (
          <button
            key={suggestion}
            className="text-left px-4 py-3 rounded-xl border border-gray-700 bg-gray-900 hover:bg-gray-800 hover:border-indigo-500 text-sm text-gray-300 transition-colors"
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
  const { messages } = useChatMessages();
  const { sendMessage } = useChatInteract();

  const flat = getMessages(messages);

  const handleSend = (content = input.trim()) => {
    if (!content) return;
    sendMessage({ name: "user", type: "user_message" as const, output: content }, []);
    setInput("");
  };

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100">
      <div className="flex justify-end p-3 border-b border-gray-800">
        <button
          className="text-gray-500 hover:text-gray-300"
          onClick={onLogout}
        >
          <LogOut size={18} />
        </button>
      </div>
      {flat.length === 0 ? (
        <WelcomeScreen onSelect={(text) => handleSend(text)} />
      ) : (
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {flat.map((m) => (
            <div key={m.id} className={`flex ${m.type === "user_message" ? "justify-end" : "justify-start"}`}>
              <span className={`px-4 py-2 rounded-xl max-w-xl text-sm whitespace-pre-wrap ${m.type === "user_message" ? "bg-indigo-600" : "bg-gray-800"}`}>
                {m.output}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2 p-4 border-t border-gray-800">
        <input
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 outline-none"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Message..."
          autoFocus
        />
        <button
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-4 py-2 rounded-lg"
          onClick={() => handleSend()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
