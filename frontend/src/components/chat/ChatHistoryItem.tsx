/**
 * One row in the sidebar's chat-history list: the conversation's title (click
 * to resume it) plus a three-dot menu for rename/delete.
 *
 * No shared dropdown/menu primitive exists yet in this app (Explore report) —
 * daisyui's `dropdown`/`menu` classes are already loaded (see `index.css`),
 * so this is the lowest-friction idiomatic choice here.
 */

import { useRef, useState } from "react";
import { MoreVertical, Trash2, Pencil, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api/client";
import type { ConversationSummary } from "@/lib/api/types";

interface Props {
  conversation: ConversationSummary;
  active: boolean;
  onSelect: () => void;
  onRenamed: (title: string) => void;
  onDeleted: () => void;
}

export function ChatHistoryItem({ conversation, active, onSelect, onRenamed, onDeleted }: Props) {
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(conversation.title || conversation.query || "Untitled chat");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  const closeMenu = () => detailsRef.current?.removeAttribute("open");

  async function submitRename(): Promise<void> {
    const next = title.trim();
    if (!next || next === conversation.title) {
      setRenaming(false);
      setTitle(conversation.title || conversation.query || "Untitled chat");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.renameConversation(conversation.conversation_id, next);
      onRenamed(next);
      setRenaming(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to rename.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(): Promise<void> {
    closeMenu();
    setBusy(true);
    setError(null);
    try {
      await api.deleteConversation(conversation.conversation_id);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete.");
      setBusy(false);
    }
  }

  if (renaming) {
    return (
      <div className="px-1">
        <input
          className="input input-xs input-bordered w-full"
          value={title}
          autoFocus
          disabled={busy}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submitRename();
            if (e.key === "Escape") {
              setRenaming(false);
              setTitle(conversation.title || conversation.query || "Untitled chat");
            }
          }}
          onBlur={() => void submitRename()}
        />
        {error && <p className="text-error text-xs px-1 pt-0.5">{error}</p>}
      </div>
    );
  }

  return (
    <div
      className={`group flex items-center gap-1 rounded-md px-1 ${
        active ? "bg-base-300" : "hover:bg-base-300/60"
      }`}
    >
      <button
        className="flex-1 min-w-0 flex items-center gap-1.5 text-left text-sm py-1.5"
        onClick={onSelect}
        disabled={busy}
        title={
          conversation.pending
            ? `${conversation.title || conversation.query} (response in progress)`
            : conversation.title || conversation.query
        }
      >
        <span className="truncate">{title}</span>
        {conversation.pending && (
          <Loader2 size={12} className="shrink-0 animate-spin text-primary" aria-label="Response in progress" />
        )}
      </button>
      <details ref={detailsRef} className="dropdown dropdown-end">
        <summary
          className="btn btn-ghost btn-xs btn-square opacity-0 group-hover:opacity-100 focus:opacity-100"
          aria-label="Chat options"
        >
          <MoreVertical size={14} />
        </summary>
        <ul className="dropdown-content menu menu-sm bg-base-100 border border-base-300 rounded-box z-10 w-32 shadow">
          <li>
            <button
              onClick={() => {
                closeMenu();
                setRenaming(true);
              }}
            >
              <Pencil size={13} /> Rename
            </button>
          </li>
          <li>
            <button className="text-error" onClick={() => void handleDelete()}>
              <Trash2 size={13} /> Delete
            </button>
          </li>
        </ul>
      </details>
      {error && !renaming && <p className="text-error text-xs px-1">{error}</p>}
    </div>
  );
}
