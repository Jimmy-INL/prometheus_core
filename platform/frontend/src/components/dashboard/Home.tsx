import { useRef } from "react";
import { Chat } from "../Chat";
import { StatusPanel } from "./StatusPanel";

/**
 * Home = the merged command center (Figma dashboard-home / -chat / -artifacts):
 * the live Chat on the left, a persistent status rail on the right. Chat is
 * always mounted — it swaps its own transcript area for the Figma welcome
 * screen while idle, and keeps its composer either way.
 *
 * The scroll container ref lives here (not in Chat) so this panel and the
 * status rail scroll independently and the scrollbar sits at the panel
 * boundary rather than hugging Chat's narrower centered message column.
 */
export function Home() {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
      <section className="flex min-w-0 flex-1 flex-col border-b border-base-300 lg:border-b-0 lg:border-r">
        <Chat scrollContainerRef={scrollRef} />
      </section>
      <aside className="flex w-full shrink-0 flex-col lg:w-96 xl:w-[26rem]">
        <StatusPanel />
      </aside>
    </div>
  );
}
