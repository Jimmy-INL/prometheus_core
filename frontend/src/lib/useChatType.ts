import { useEffect, useState } from "react";

export const CHAT_TYPES = ["Beginner", "Advanced"] as const;
export type ChatType = (typeof CHAT_TYPES)[number];
export const DEFAULT_CHAT_TYPE: ChatType = "Beginner";

export const CHAT_TYPE_DESCRIPTIONS: Record<ChatType, string> = {
  Beginner: "This profile provides some suggestions on how to get started.",
  Advanced: "This profile doesn't provide any suggestions.",
};

const STORAGE_KEY = "prometheus.chatType";
const CHANGE_EVENT = "prometheus.chatType.change";

/** Map the local UI chat type to the backend chat-profile name. */
export function chatProfileName(t: ChatType): string {
  return t === "Advanced" ? "Advanced Chat" : "Beginner Chat";
}

function read(): ChatType {
  const v = localStorage.getItem(STORAGE_KEY);
  return v === "Advanced" || v === "Beginner" ? v : DEFAULT_CHAT_TYPE;
}

export function useChatType(): [ChatType, (next: ChatType) => void] {
  const [value, setValue] = useState<ChatType>(read);

  useEffect(() => {
    const sync = () => setValue(read());
    window.addEventListener("storage", sync);
    window.addEventListener(CHANGE_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(CHANGE_EVENT, sync);
    };
  }, []);

  const update = (next: ChatType) => {
    localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  };

  return [value, update];
}
