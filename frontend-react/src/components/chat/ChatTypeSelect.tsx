import { useId } from "react";
import {
  CHAT_TYPES,
  CHAT_TYPE_DESCRIPTIONS,
  ChatType,
} from "@/lib/useChatType";

export function ChatTypeSelect({
  value,
  onChange,
}: {
  value: ChatType;
  onChange: (next: ChatType) => void;
}) {
  const groupId = useId();

  return (
    <div className="grid h-12 w-full grid-cols-2 rounded-lg border border-base-300 bg-base-200 p-1">
      {CHAT_TYPES.map((t) => {
        const selected = value === t;
        const inputId = `${groupId}-${t.toLowerCase()}`;
        return (
          <div key={t} className="relative min-w-0">
            <input
              id={inputId}
              className="peer sr-only"
              type="radio"
              name={groupId}
              value={t}
              checked={selected}
              onChange={() => onChange(t)}
              aria-label={`${t}: ${CHAT_TYPE_DESCRIPTIONS[t]}`}
            />
            <label
              htmlFor={inputId}
              title={CHAT_TYPE_DESCRIPTIONS[t]}
              className={`flex h-full min-w-0 cursor-pointer items-center justify-center rounded-lg px-3 text-sm font-bold transition-colors peer-focus-visible:outline peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary 
                ${selected
                  ? "bg-primary text-primary-content shadow-sm"
                  : "text-base-content/70 hover:bg-base-100 hover:text-base-content"
                }`
              }
            >
              <span className="truncate">{t}</span>
            </label>
          </div>
        );
      })}
    </div>
  );
}
