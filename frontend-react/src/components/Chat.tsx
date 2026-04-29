import { useState } from "react";
import { useChatMessages, useChatInteract, IStep } from "@chainlit/react-client";

function getMessages(messages: IStep[]): IStep[] {
  return messages.flatMap((m) => {
    const children = m.steps ? getMessages(m.steps) : [];
    if (m.type === "user_message" || m.type === "assistant_message") {
      return [m, ...children];
    }
    return children;
  });
}

export function Chat() {
  const [input, setInput] = useState("");
  const { messages } = useChatMessages();
  const { sendMessage } = useChatInteract();

  const flat = getMessages(messages);

  const handleSend = () => {
    const content = input.trim();
    if (!content) return;
    sendMessage({ name: "user", type: "user_message" as const, output: content }, []);
    setInput("");
  };

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100">
      <div className="flex-1 overflow-y-auto p-5 space-y-3">
        {flat.map((m) => (
          <div key={m.id} className={`flex ${m.type === "user_message" ? "justify-end" : "justify-start"}`}>
            <span className={`px-4 py-2 rounded-xl max-w-xl text-sm whitespace-pre-wrap ${m.type === "user_message" ? "bg-indigo-600" : "bg-gray-800"}`}>
              {m.output}
            </span>
          </div>
        ))}
      </div>
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
          onClick={handleSend}
        >
          Send
        </button>
      </div>
    </div>
  );
}
