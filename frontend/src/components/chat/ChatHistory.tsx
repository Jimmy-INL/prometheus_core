/**
 * Chat-history list rendered in `LeftPanel`'s sidebar, under "New chat".
 *
 * Fetches `GET /api/conversations/recent` (already user-scoped server-side —
 * see `backend/app/routers/conversations.py`) and re-fetches whenever
 * `historyVersion` changes (a turn completed, a new chat started, or a past
 * one was opened — see `lib/store/chat.ts`). Degrades to nothing rendered
 * when Redis is unavailable, matching the endpoint's graceful-degrade shape.
 *
 * `historyVersion` only bumps for events on the *currently open* conversation,
 * so a different conversation's own background turn finishing wouldn't
 * otherwise clear its "pending" badge (`ConversationSummary.pending`, from
 * `agent:status:{id}`) until something else happened to trigger a refetch.
 * While any row is pending, a short poll picks that up without needing full
 * per-conversation live tracking (see the "Prometheus Chat History Pending
 * Response Handling" note for why that's future work, not this).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { chatStore, useChatState } from "@/lib/store/chat";
import type { ConversationSummary } from "@/lib/api/types";
import { ChatHistoryItem } from "./ChatHistoryItem";

const PENDING_POLL_MS = 8000;

export function ChatHistory() {
  const { conversationId, historyVersion } = useChatState();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(() => {
    void api
      .getRecentConversations()
      .then((res) => setConversations(res.available ? res.conversations : []))
      .catch(() => setConversations([]))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch on every history-affecting event
  }, [historyVersion, refresh]);

  const anyPending = conversations.some((c) => c.pending);
  useEffect(() => {
    if (!anyPending) return;
    pollRef.current = setInterval(refresh, PENDING_POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [anyPending, refresh]);

  if (!loaded || conversations.length === 0) return null;

  return (
    <div className="flex flex-col gap-0.5 py-1">
      <div className="px-2 pb-1 text-xs font-medium uppercase text-base-content/40">Recent chats</div>
      {conversations.map((c) => (
        <ChatHistoryItem
          key={c.conversation_id}
          conversation={c}
          active={c.conversation_id === conversationId}
          onSelect={() => void chatStore.loadConversation(c.conversation_id)}
          onRenamed={(title) =>
            setConversations((prev) =>
              prev.map((it) => (it.conversation_id === c.conversation_id ? { ...it, title } : it)),
            )
          }
          onDeleted={() =>
            setConversations((prev) => prev.filter((it) => it.conversation_id !== c.conversation_id))
          }
        />
      ))}
    </div>
  );
}
