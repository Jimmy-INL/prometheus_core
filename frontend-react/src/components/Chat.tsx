import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Square, ChevronDown, ChevronRight, Wrench, Copy, Check, Paperclip, X, FileText, Loader2 } from "lucide-react";
import {
  useChatMessages,
  useChatInteract,
  elementState,
  actionState,
  askUserState,
  IAction,
  IFileRef,
} from "@chainlit/react-client";
import { useRecoilValue } from "recoil";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatIntro, chatSuggestionTitle, workflowSuggestions } from "../config";
import { useChatType } from "@/lib/useChatType";
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
import { ElementList } from "./ElementRenderer";
import type { AnyElement } from "../lib/chainlit/elements";
// ViewerTestHarness is to render Viewers for testing outside of the Chat
// import { ViewerTestHarness } from "../dev/ViewerTestHarness"; 

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

function ToolStep({ item }: { item: FlatItem }) {
  const [open, setOpen] = useState(false);
  const { step } = item;
  // A running step arrives over the socket with `end: null` (JSON), not
  // undefined — so compare against null to catch both. `end !== undefined`
  // alone was always true for in-progress steps, so nothing ever animated.
  const isDone = !step.waitForAnswer && step.end != null;
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
          <span className={isDone ? "" : "italic text-shimmer"}>
            {step.name || "Processing…"}
          </span>
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

function WelcomeScreen({ onSelect }: { onSelect: (text: string) => void }) {
  const [chatType] = useChatType();
  const showSuggestions = chatType === "Beginner";
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-6 gap-8">
      <div className="text-center space-y-2">
        <h1>{chatIntro}</h1>
        {showSuggestions && <p className="text-base-content">{chatSuggestionTitle}</p>}
      </div>
      {showSuggestions && (
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
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

interface Attachment {
  localId: string;
  file: File;
  uploading: boolean;
  id?: string;
  error?: string;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Main Chat component
// ---------------------------------------------------------------------------

interface ChatProps {
  // Owned by the parent (ProjectView) so that, once a second panel (artifact
  // viewer) is added alongside Chat, each panel scrolls independently and
  // the scrollbar sits at the panel boundary rather than hugging the
  // narrower max-w-4xl message column. Chat still owns all the scroll
  // *behavior* (autoscroll, spacer sizing, near-bottom detection) — only
  // the DOM node + its overflow styling live one level up.
  scrollContainerRef: React.RefObject<HTMLDivElement>;
}

export function Chat({ scrollContainerRef }: ChatProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastUserMessageRef = useRef<HTMLDivElement>(null);
  const lastAssistantMessageRef = useRef<HTMLDivElement>(null);
  const loadingDotsRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const prevUserCountRef = useRef(0);
  const programmaticScrollUntilRef = useRef(0);
  const [awaitingResponse, setAwaitingResponse] = useState(false);

  const { messages } = useChatMessages();
  const { sendMessage, stopTask, uploadFile } = useChatInteract();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const uploadingCount = attachments.filter((a) => a.uploading).length;

  const handlePickFiles = () => fileInputRef.current?.click();

  const handleFilesSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;

    const next: Attachment[] = [];
    for (const file of files) {
      const localId = `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`;
      if (file.size > MAX_UPLOAD_BYTES) {
        next.push({ localId, file, uploading: false, error: "File exceeds 100 MB limit" });
        continue;
      }
      const att: Attachment = { localId, file, uploading: true };
      next.push(att);

      const { promise } = uploadFile(file, () => {});
      promise
        .then(({ id }) => {
          setAttachments((prev) =>
            prev.map((a) => (a.localId === localId ? { ...a, uploading: false, id } : a)),
          );
        })
        .catch((err: unknown) => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.localId === localId
                ? { ...a, uploading: false, error: err instanceof Error ? err.message : "Upload failed" }
                : a,
            ),
          );
        });
    }
    setAttachments((prev) => [...prev, ...next]);
  };

  const removeAttachment = (localId: string) =>
    setAttachments((prev) => prev.filter((a) => a.localId !== localId));

  const globalElements = useRecoilValue(elementState);
  const globalActions = useRecoilValue(actionState);
  const askUser = useRecoilValue(askUserState);

  useEffect(() => {
    console.log(
      `[askUser ${new Date().toISOString().slice(11, 23)}]`,
      askUser
        ? { type: askUser.spec.type, parentId: askUser.parentId, spec: askUser.spec }
        : null,
    );
  }, [askUser]);

  // Prefill the composer from a ?prompt= query param (deep-link support).
  // Populates the input only — never auto-sends — so a shared/crafted link
  // can't push a message on the user's behalf. The user must still hit
  // send or Enter. Runs once on mount, then scrubs the param from the URL
  // so a refresh doesn't re-fill the box or leave it in browser history.
  //
  // Accepts a few forms, in order of readability:
  //   ?prompt="Show me the thermal analysis"   (quotes, spaces — most readable, stripped below)
  //   ?prompt=Show me the thermal analysis     (raw spaces, no quotes — browsers auto-encode this,
  //                                              but scripts/tools that build URLs manually may not)
  //   ?prompt=Show+me+the+thermal+analysis     (+ for spaces, no quotes — always safe, still readable)
  //   ?prompt=Show%20me%20the%20thermal...     (fully encoded — least readable, always safe)
  // Wrapping quotes are optional and purely cosmetic. A prompt that must
  // literally start/end with a quote should escape it as %22 instead of
  // using a bare ".
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    let prefill = params.get("prompt");
    if (prefill) {
      if (prefill.startsWith('"') && prefill.endsWith('"') && prefill.length >= 2) {
        prefill = prefill.slice(1, -1);
      }
      setInput(prefill);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  const flat = flattenMessages(messages);

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
    const el = scrollContainerRef.current;
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
  }, [awaitingResponse, lastMessage?.type, scrollContainerRef]);

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
        const el = scrollContainerRef.current;
        if (!target || !el) return;
        programmaticScrollUntilRef.current = Date.now() + 800;
        el.scrollTo({ top: target.offsetTop - el.offsetTop - 16, behavior: "smooth" });
      });
    }
    prevUserCountRef.current = userCount;
  }, [flat, scrollContainerRef]);

  useEffect(() => {
    const el = scrollContainerRef.current;
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
  }, [lastMessage?.output, lastMessage?.type, lastMessage?.id, awaitingResponse, flat.length, scrollContainerRef]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (Date.now() < programmaticScrollUntilRef.current) return;
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = nearBottom;
  };

  const handleSend = (content = input.trim()) => {
    const readyRefs: IFileRef[] = attachments
      .filter((a) => a.id && !a.error)
      .map((a) => ({ id: a.id as string }));
    if (!content && !readyRefs.length) return;
    if (uploadingCount > 0) return;
    sendMessage({ name: "user", type: "user_message" as const, output: content }, readyRefs);
    setInput("");
    setAttachments([]);
    setAwaitingResponse(true);
  };

  const handleStop = () => {
    stopTask();
    setAwaitingResponse(false);
  };

  const handleAction = (action: IAction) => {
    if (askUser) {
      askUser.callback(action);
    } else {
      console.warn("Action ask is no longer active (timed out or cleared).");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const showLoadingDots =
    awaitingResponse &&
    lastMessage?.type === "user_message" &&
    !lastMessage.waitForAnswer;

  return (
    <div className="flex flex-col flex-1 w-full overflow-hidden">
      {/* For testing Viewers, uncomment the line below and its import and edit Test Harness */} 
      {/* <ViewerTestHarness /> */} 
      {flat.length === 0 ? (
        <WelcomeScreen onSelect={(text) => handleSend(text)} />
      ) : (
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto"
        >
          <div className="max-w-4xl mx-auto p-5 space-y-5">
            {flat.map((item: FlatItem, i: number) => {
              const { step: m } = item;

              const joinedActions = item.actions.length
                ? item.actions
                : globalActions.filter((a) => a.forId === m.id);
              const effective: FlatItem =
                joinedActions.length && item.kind !== "ask_action"
                  ? { ...item, actions: joinedActions, kind: "ask_action" }
                  : joinedActions.length !== item.actions.length
                  ? { ...item, actions: joinedActions }
                  : item;

              if (isToolStep(effective) || isAskPlain(effective)) {
                return (
                  <div key={m.id} className="space-y-2">
                    <ToolStep item={effective} />
                  </div>
                );
              }

              if (isAskForm(effective)) {
                const askElements = [
                  ...((m.elements as AnyElement[] | undefined) ?? []),
                  ...(globalElements.filter((e) => e.forId === m.id) as unknown as AnyElement[]),
                ];
                return (
                  <div key={m.id} className="flex gap-2 justify-start">
                    <AssistantAvatar />
                    <div className="flex-1 text-base text-base-content [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                      {m.output && (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {m.output}
                        </ReactMarkdown>
                      )}
                      <ElementList elements={askElements} onSend={handleSend} />
                    </div>
                  </div>
                );
              }

              if (isAskAction(effective)) {
                const askElements = [
                  ...((m.elements as AnyElement[] | undefined) ?? []),
                  ...(globalElements.filter((e) => e.forId === m.id) as unknown as AnyElement[]),
                ];
                return (
                  <div key={m.id} className="flex gap-2 justify-start">
                    <AssistantAvatar />
                    <div className="flex-1 text-base text-base-content [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
                      {m.output && (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {m.output}
                        </ReactMarkdown>
                      )}
                      <ElementList elements={askElements} onSend={handleSend} />
                      <ActionButtons item={effective} onAction={handleAction} />
                    </div>
                  </div>
                );
              }

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
                    m.output ? (
                      <span className="px-4 py-2 rounded-xl max-w-xl text-base whitespace-pre-wrap bg-base-300 text-base-content">
                        {m.output}
                      </span>
                    ) : null
                  ) : (
                    <>
                      <AssistantAvatar />
                      <div className="flex-1 text-base text-base-content [&_p]:text-[length:inherit] [&_p]:leading-normal [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_a]:underline">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {m.output}
                        </ReactMarkdown>
                        <ElementList
                          elements={[
                            ...((m.elements as AnyElement[] | undefined) ?? []),
                            ...(globalElements.filter((e) => e.forId === m.id) as unknown as AnyElement[]),
                          ]}
                          onSend={handleSend}
                        />
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
        </div>
      )}

      <div className="px-4 pt-3 pb-2">
        <div className="max-w-4xl mx-auto">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="*/*"
            className="hidden"
            onChange={handleFilesSelected}
          />
          <div className="rounded-3xl border border-base-300 bg-base-200 shadow-sm focus-within:border-primary/60 focus-within:shadow-md transition-all">
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 px-3 pt-3">
                {attachments.map((a) => (
                  <div
                    key={a.localId}
                    className={`flex items-center gap-2 rounded-full pl-2 pr-1 py-1 text-xs ${
                      a.error
                        ? "bg-error/10 text-error"
                        : "bg-base-300 text-base-content"
                    }`}
                    title={a.error ?? `${a.file.name} (${formatBytes(a.file.size)})`}
                  >
                    {a.uploading ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <FileText size={12} />
                    )}
                    <span className="max-w-45 truncate">{a.file.name}</span>
                    <span className="text-base-content/50">{formatBytes(a.file.size)}</span>
                    <button
                      onClick={() => removeAttachment(a.localId)}
                      className="rounded-full p-0.5 hover:bg-base-100"
                      aria-label={`Remove ${a.file.name}`}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="relative flex items-end">
              <button
                className="btn btn-ghost btn-circle btn-sm absolute bottom-2.5 left-2.5"
                onClick={handlePickFiles}
                disabled={awaitingResponse}
                aria-label="Attach files"
              >
                <Paperclip size={16} />
              </button>
              <textarea
                ref={textareaRef}
                className="flex-1 bg-transparent resize-none outline-none pl-14 pr-14 py-4 text-base leading-6 placeholder:text-base-content/50 max-h-50"
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
                disabled={
                  !awaitingResponse &&
                  !input.trim() &&
                  attachments.filter((a) => a.id && !a.error).length === 0
                }
                aria-label={awaitingResponse ? "Stop response" : "Send message"}
              >
                {awaitingResponse ? (
                  <Square size={14} fill="currentColor" />
                ) : uploadingCount > 0 ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <ArrowUp size={18} />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
      <p className="text-center text-xs text-base-content/70 pb-2">
        LLMs can make mistakes. Check important info.
      </p>
    </div>
  );
}
