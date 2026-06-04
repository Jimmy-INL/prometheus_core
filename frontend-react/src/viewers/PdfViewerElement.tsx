/**
 * src/viewers/PdfViewerElement.tsx
 *
 * Renders a Chainlit cl.Pdf element as an inline iframe.
 *
 * URL resolution
 * ──────────────
 * Chainlit 2.x sends PDF elements with an `id` but no `url`. The URL is
 * resolved via apiClient.getElementUrl(id, sessionId) — the same method
 * the default Chainlit frontend uses internally.
 */

import { useContext } from "react";
import { useRecoilValue } from "recoil";
import { ChainlitContext, sessionState } from "@chainlit/react-client";
import { FileDown } from "lucide-react";
import type { ViewerProps } from "@/lib/chainlit/elements";

export function PdfViewerElement({ element }: ViewerProps) {
  const apiClient = useContext(ChainlitContext);
  const session = useRecoilValue(sessionState);
  const sessionId = session?.socket.id;

  const url =
    element.url ??
    (element.id && sessionId && apiClient
      ? apiClient.getElementUrl(element.id, sessionId)
      : null);

  if (!url) return null;

  const name = element.name ?? "document.pdf";

  return (
    <div className="border border-base-300 rounded-lg overflow-hidden my-2 bg-base-200/40 max-w-3xl">
      <div className="flex items-center justify-between px-3 py-2 border-b border-base-300 bg-base-200/60">
        <p className="text-sm font-medium text-base-content truncate">{name}</p>
        <a
          href={url}
          download={name}
          className="btn btn-ghost btn-xs shrink-0"
          aria-label={`Download ${name}`}
        >
          <FileDown size={13} />
          Download
        </a>
      </div>
      <iframe
        src={url}
        title={name}
        className="w-full h-[600px] bg-base-100"
      />
    </div>
  );
}
