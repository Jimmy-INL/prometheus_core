import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { useChatMessages, useChatInteract, IStep } from "@chainlit/react-client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatIntro, chatSuggestionTitle, workflowSuggestions } from "../config";

function getMessages(messages: IStep[]): IStep[] {
  return messages.flatMap((m) => {
    const children = m.steps ? getMessages(m.steps) : [];
    if (m.type === "user_message" || m.type === "assistant_message") {
      return [m, ...children];
    }
    return children;
  });
}

const AssistantAvatar = () => (
  <img
    src="/images/Prometheus_mark_white.png"
    alt="Prometheus"
    className="w-6 h-6 rounded-full shrink-0 bg-neutral object-contain p-1"
  />
);

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

export function Chat() {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastUserMessageRef = useRef<HTMLDivElement>(null);
  const lastAssistantMessageRef = useRef<HTMLDivElement>(null);
  const loadingDotsRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const prevUserCountRef = useRef(0);
  const programmaticScrollUntilRef = useRef(0);
  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const { messages } = useChatMessages();
  const { sendMessage, stopTask } = useChatInteract();

  const flat = getMessages(messages);
  const lastMessage = flat[flat.length - 1];
  let lastUserIdx = -1;
  let lastAssistantIdx = -1;
  for (let i = flat.length - 1; i >= 0; i--) {
    if (lastUserIdx === -1 && flat[i].type === "user_message") lastUserIdx = i;
    if (lastAssistantIdx === -1 && flat[i].type === "assistant_message") lastAssistantIdx = i;
    if (lastUserIdx !== -1 && lastAssistantIdx !== -1) break;
  }

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

  // Size the bottom spacer just large enough to let the last user message reach the top of
  // the viewport — and no larger. Shrinks to 0 once the assistant reply is long enough on its own.
  const updateSpacer = useCallback(() => {
    const el = scrollRef.current;
    const userMsg = lastUserMessageRef.current;
    const spacer = spacerRef.current;
    if (!spacer) return;
    if (!el || !userMsg) {
      spacer.style.minHeight = "0px";
      return;
    }
    const tail =
      awaitingResponse && lastMessage?.type === "user_message"
        ? loadingDotsRef.current
        : lastAssistantMessageRef.current ?? userMsg;
    if (!tail) {
      spacer.style.minHeight = "0px";
      return;
    }
    spacer.style.minHeight = "0px";
    const tailBottom = tail.offsetTop + tail.offsetHeight;
    const needed = Math.max(0, el.clientHeight - (tailBottom - userMsg.offsetTop) - 16);
    spacer.style.minHeight = `${needed}px`;
  }, [awaitingResponse, lastMessage?.type]);

  useLayoutEffect(() => {
    updateSpacer();
  }, [updateSpacer, lastMessage?.output, lastMessage?.id, flat.length, awaitingResponse]);

  useEffect(() => {
    window.addEventListener("resize", updateSpacer);
    return () => window.removeEventListener("resize", updateSpacer);
  }, [updateSpacer]);

  // When a new user message is sent: pin it to the top of the viewport and re-enable auto-scroll.
  useEffect(() => {
    const userCount = flat.filter((m) => m.type === "user_message").length;
    if (userCount > prevUserCountRef.current) {
      autoScrollRef.current = true;
      requestAnimationFrame(() => {
        const target = lastUserMessageRef.current;
        const el = scrollRef.current;
        if (!target || !el) return;
        programmaticScrollUntilRef.current = Date.now() + 800;
        el.scrollTo({ top: target.offsetTop - el.offsetTop - 16, behavior: "smooth" });
      });
    }
    prevUserCountRef.current = userCount;
  }, [flat]);

  // Follow the bottom of the assistant reply — but only if its bottom is below the viewport.
  // Never scroll past the actual content (the bottom spacer would otherwise overshoot).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !autoScrollRef.current) return;
    const target =
      awaitingResponse && lastMessage?.type === "user_message"
        ? loadingDotsRef.current
        : lastAssistantMessageRef.current;
    if (!target) return;
    const targetBottom = target.offsetTop - el.offsetTop + target.offsetHeight;
    const desired = targetBottom - el.clientHeight + 24;
    if (desired > el.scrollTop) {
      programmaticScrollUntilRef.current = Date.now() + 400;
      el.scrollTop = desired;
    }
  }, [lastMessage?.output, lastMessage?.type, lastMessage?.id, awaitingResponse, flat.length]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (Date.now() < programmaticScrollUntilRef.current) return;
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = nearBottom;
  };

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
    <div className="flex flex-col flex-1 w-full max-w-4xl mx-auto overflow-hidden">
      {flat.length === 0 ? (
        <WelcomeScreen onSelect={(text) => handleSend(text)} />
      ) : (
        <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-5 space-y-5">
          {flat.map((m, i) => (
            <div
              key={m.id}
              ref={
                i === lastUserIdx
                  ? lastUserMessageRef
                  : i === lastAssistantIdx
                  ? lastAssistantMessageRef
                  : undefined
              }
              className={`flex gap-2 ${m.type === "user_message" ? "justify-end" : "justify-start"}`}
            >
                  {m.type === "user_message" ? (
                    <span className="px-4 py-2 rounded-xl max-w-xl text-base whitespace-pre-wrap bg-base-300 text-base-content">
                      {m.output}
                    </span>
                  ) : (
                    <>
                      <AssistantAvatar />
                      <div className="flex-1 text-base text-base-content [&_p]:text-[length:inherit] [&_p]:leading-normal [&_span]:text-[length:inherit] [&_li]:text-[length:inherit] [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:bg-base-300 [&_pre]:bg-base-300 [&_pre]:p-2 [&_pre]:rounded [&_pre]:my-2 [&_pre]:overflow-x-auto [&_a]:underline">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.output}</ReactMarkdown>
                      </div>
                    </>
                  )}
            </div>
          ))}
              {awaitingResponse && lastMessage?.type === "user_message" && (
                <div ref={loadingDotsRef} className="flex gap-2 justify-start" aria-live="polite" aria-label="Assistant is thinking">
                  <AssistantAvatar />
                  <span className="loading loading-dots loading-md text-base-content self-center" />
                </div>
              )}
              <div ref={spacerRef} aria-hidden />
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
    </div>
  );
}
