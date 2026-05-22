import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Square, ChevronDown, ChevronRight, Wrench, Copy, Check } from "lucide-react";
import {
  useChatMessages,
  useChatInteract,
  ChainlitContext,
  sessionState,
  IAction,
} from "@chainlit/react-client";
import { useRecoilValue } from "recoil";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatIntro, chatSuggestionTitle, workflowSuggestions } from "../config";
import {
  flattenMessages,
  FlatItem,
  isUserMessage,
  isAssistantMessage,
  isToolStep,
  isAskAction,
  isAskForm,
  isAskPlain,
} from "../lib/chainlit/chainlit";

// ---------------------------------------------------------------------------
// Markdown renderers
// ---------------------------------------------------------------------------

function CodeBlock({ children, className }: { children?: React.ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");
  const isBlock = code.includes("\n");

  if (!isBlock) {
    return (
      <code className={`px-1 py-0.5 rounded bg-base-300 text-sm ${className ?? ""}`}>
        {children}
      </code>
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="relative group my-2">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity bg-base-100/50 hover:bg-base-100 text-base-content/50 hover:text-base-content"
        aria-label="Copy code"
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </button>
      <pre className="bg-base-300 rounded p-3 overflow-x-auto text-sm leading-5">
        <code className={className}>{code}</code>
      </pre>
    </div>
  );
}

// TODO: Syntax highlighting for code blocks
// Add react-syntax-highlighter or shiki when the time comes.
// When implemented, detect language from className (e.g. "language-python") and
// only apply highlighting when a language is explicitly tagged — untagged blocks
// (ASCII diagrams, plain text) should render as-is without highlighting attempts.
const markdownComponents = {
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => (
    <CodeBlock className={className}>{children}</CodeBlock>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto my-2">
      <table className="table table-sm">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: React.ReactNode }) => (
    <thead className="bg-base-300">{children}</thead>
  ),
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-xl font-bold mt-4 mb-2">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-lg font-semibold mt-3 mb-1">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-base font-semibold mt-2 mb-1">{children}</h3>
  ),
  hr: () => <hr className="border-base-300 my-3" />,
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const AssistantAvatar = () => (
  <img
    src="/images/Prometheus_mark_white.png"
    alt="Prometheus"
    className="w-6 h-6 rounded-full shrink-0 bg-neutral object-contain p-1"
  />
);

/** Collapsible status step rendered from cl.Step(type="tool") */
function ToolStep({ item }: { item: FlatItem }) {
  const [open, setOpen] = useState(false);
  const { step } = item;
  const isDone = !step.waitForAnswer && step.end !== undefined;
  const hasHistory = Boolean(step.output?.trim());

  return (
    <div className="flex gap-2 justify-start">
      <div className="w-6 h-6 shrink-0 flex items-center justify-center">
        <Wrench
          size={13}
          className={isDone ? "text-base-content/30" : "text-primary animate-pulse"}
        />
      </div>
      <div className="flex flex-col gap-0.5 max-w-xl">
        <button
          className="flex items-center gap-1 text-sm text-base-content/50 hover:text-base-content/70 transition-colors text-left"
          onClick={() => setOpen((v) => !v)}
          disabled={!hasHistory}
        >
          {hasHistory ? (
            open ? <ChevronDown size={13} /> : <ChevronRight size={13} />
          ) : (
            <span className="w-3.25" />
          )}
          <span className={isDone ? "" : "italic"}>{step.name || "Processing…"}</span>
          {!isDone && (
            <span className="loading loading-dots loading-xs ml-1 text-base-content/40" />
          )}
        </button>
        {open && hasHistory && (
          <pre className="text-xs text-base-content/40 bg-base-300 rounded p-2 whitespace-pre-wrap leading-5 mt-1">
            {step.output}
          </pre>
        )}
      </div>
    </div>
  );
}

/** Approve/Reject buttons from cl.AskActionMessage */
function ActionButtons({
  item,
  onAction,
}: {
  item: FlatItem;
  onAction: (action: IAction) => void;
}) {
  if (!item.actions.length) return null;

  return (
    <div className="flex gap-2 justify-start pl-8">
      {item.actions.map((action) => {
        const isApprove =
          action.name === "approve" ||
          action.label?.toLowerCase().includes("approve") ||
          action.label?.toLowerCase().includes("execute");
        return (
          <button
            key={action.id ?? action.name}
            className={`btn btn-sm ${isApprove ? "btn-primary" : "btn-ghost border border-base-300"}`}
            onClick={() => onAction(action)}
          >
            {action.label ?? action.name}
          </button>
        );
      })}
    </div>
  );
}

// TODO: AskFormStep component
// Renders cl.AskElementMessage flows (DynamicForm, PlanViewer).
// Blocked on CustomElement registry implementation in src/lib/chainlit/chainlit.ts.
// For now, ask_form items fall through to ToolStep (shows name + spinner),
// which is harmless — user just can't respond to the form yet.

// TODO: AskPlainStep component
// Renders cl.AskUserMessage with an inline text input.
// Rare in current backend but should be handled before considering chat complete.

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

// ---------------------------------------------------------------------------
// Main Chat component
// ---------------------------------------------------------------------------

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
  const apiClient = useContext(ChainlitContext);
  const session = useRecoilValue(sessionState);

  const flat = flattenMessages(messages);

  // Indices for scroll anchoring
  let lastUserIdx = -1;
  let lastAssistantIdx = -1;
  for (let i = flat.length - 1; i >= 0; i--) {
    if (lastUserIdx === -1 && isUserMessage(flat[i])) lastUserIdx = i;
    if (lastAssistantIdx === -1 && isAssistantMessage(flat[i])) lastAssistantIdx = i;
    if (lastUserIdx !== -1 && lastAssistantIdx !== -1) break;
  }

  const lastItem: FlatItem | undefined = flat[flat.length - 1];
  const lastMessage = lastItem?.step;

  useEffect(() => {
    if (lastMessage?.type === "assistant_message") {
      setAwaitingResponse(false);
    }
  }, [lastMessage?.id, lastMessage?.type]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

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

  useEffect(() => {
    const userCount = flat.filter(isUserMessage).length;
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

  const handleAction = async (action: IAction) => {
    if (!apiClient || !session?.socket.id) return;
    await apiClient.callAction(action, session.socket.id);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // Show loading dots only when awaiting a response and not waiting for user input
  const showLoadingDots =
    awaitingResponse &&
    lastMessage?.type === "user_message" &&
    !lastMessage.waitForAnswer;

  return (
    <div className="flex flex-col flex-1 w-full max-w-4xl mx-auto overflow-hidden">
      {flat.length === 0 ? (
        <WelcomeScreen onSelect={(text) => handleSend(text)} />
      ) : (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-5 space-y-5"
        >
          {flat.map((item: FlatItem, i: number) => {
            const { step: m } = item;

            // Tool step (includes ask_form fallthrough until CustomElement registry exists)
            if (isToolStep(item) || isAskForm(item) || isAskPlain(item)) {
              return (
                <div key={m.id} className="space-y-2">
                  <ToolStep item={item} />
                </div>
              );
            }

            // Ask action — tool step + action buttons
            if (isAskAction(item)) {
              return (
                <div key={m.id} className="space-y-2">
                  <ToolStep item={item} />
                  <ActionButtons item={item} onAction={handleAction} />
                </div>
              );
            }

            // User / assistant messages
            return (
              <div
                key={m.id}
                ref={
                  i === lastUserIdx
                    ? lastUserMessageRef
                    : i === lastAssistantIdx
                    ? lastAssistantMessageRef
                    : undefined
                }
                className={`flex gap-2 ${
                  isUserMessage(item) ? "justify-end" : "justify-start"
                }`}
              >
                {isUserMessage(item) ? (
                  <span className="px-4 py-2 rounded-xl max-w-xl text-base whitespace-pre-wrap bg-base-300 text-base-content">
                    {m.output}
                  </span>
                ) : (
                  <>
                    <AssistantAvatar />
                    <div className="flex-1 text-base text-base-content [&_p]:text-[length:inherit] [&_p]:leading-normal [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_a]:underline">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {m.output}
                      </ReactMarkdown>
                    </div>
                  </>
                )}
              </div>
            );
          })}

          {showLoadingDots && (
            <div
              ref={loadingDotsRef}
              className="flex gap-2 justify-start"
              aria-live="polite"
              aria-label="Assistant is thinking"
            >
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
            {awaitingResponse ? (
              <Square size={14} fill="currentColor" />
            ) : (
              <ArrowUp size={18} />
            )}
          </button>
        </div>
      </div>
      <p className="text-center text-xs text-base-content/70 pb-2">
        LLMs can make mistakes. Check important info.
      </p>
    </div>
  );
}
