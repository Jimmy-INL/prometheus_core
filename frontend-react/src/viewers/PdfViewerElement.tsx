import { FileDown } from "lucide-react";
import type { ViewerProps } from "@/lib/chainlit/elements";

export function PdfViewerElement({ element }: ViewerProps) {
  const url = element.url;
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
