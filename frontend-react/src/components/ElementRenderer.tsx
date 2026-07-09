/**
 * src/components/ElementRenderer.tsx
 *
 * Dispatches a Chainlit element to the right viewer, or shows a fallback.
 *
 * Usage — inside the assistant message block in Chat.tsx:
 *
 *   <ElementList elements={m.elements as AnyElement[]} onSend={handleSend} />
 *
 * Also add to Chat.tsx imports:
 *   import { ElementList } from "./ElementRenderer";
 *   import type { AnyElement } from "../lib/chainlit/elements";
 *
 * Also add to IStepExtended in chainlit.ts:
 *   elements?: AnyElement[];
 */

import { Component, Suspense } from "react";
import { FileDown, AlertCircle } from "lucide-react";
import {
  classifyElement,
  VIEWER_REGISTRY,
  type AnyElement,
  type ViewerProps,
} from "../lib/chainlit/elements";

// ---------------------------------------------------------------------------
// Error boundary
// ---------------------------------------------------------------------------

class ViewerErrorBoundary extends Component<
  { children: React.ReactNode },
  { crashed: boolean }
> {
  state = { crashed: false };
  static getDerivedStateFromError() { return { crashed: true }; }
  render() {
    if (this.state.crashed) {
      return (
        <div className="flex items-center gap-2 text-sm text-error/70 bg-error/10 rounded px-3 py-2 my-1">
          <AlertCircle size={14} />
          <span>Viewer crashed.</span>
        </div>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Fallback — shown when no viewer is registered for this element kind
// ---------------------------------------------------------------------------

function NoViewerFallback({ element }: { element: AnyElement }) {
  const name = element.name ?? "Attachment";
  const url  = element.url;

  if (!url) return null;

  return (
    <div className="flex items-center gap-3 bg-base-200 border border-base-300 rounded-lg px-3 py-2.5 my-2 max-w-sm">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-base-content truncate">{name}</p>
        <p className="text-xs text-base-content/40 mt-0.5">No viewer available yet</p>
      </div>
      {url && (
        <a
          href={url}
          download={name}
          className="btn btn-ghost btn-xs shrink-0"
          aria-label={`Download ${name}`}
        >
          <FileDown size={13} />
          Download
        </a>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single element dispatcher
// ---------------------------------------------------------------------------

function ElementRenderer({ element, onSend }: ViewerProps) {
  const kind   = classifyElement(element);
  const Viewer = VIEWER_REGISTRY[kind];

  const inner = Viewer
    ? <Suspense fallback={null}><Viewer element={element} onSend={onSend} /></Suspense>
    : <NoViewerFallback element={element} />;

  return <ViewerErrorBoundary>{inner}</ViewerErrorBoundary>;
}

// ---------------------------------------------------------------------------
// List renderer — drop this into Chat.tsx
// ---------------------------------------------------------------------------

function elementId(el: AnyElement): string {
  return (el as { id?: string }).id ?? "";
}

function propName(el: AnyElement): string {
  return typeof el.props?.name === "string" ? el.props.name : "";
}

// For `file`/`image`/`pdf` elements, `el.name` genuinely is the filename.
// For `custom` elements, `el.name` is the Chainlit component type identifier
// (e.g. "SVGViewer", "PlanViewer") — the same string classifyElement()
// switches on — not a display name. The real filename for a custom element
// lives in props.name instead (see ImageViewerElement, which already checks
// props.name before element.name for this reason). Getting this backwards
// is why a custom SVGViewer element and its companion file element never
// matched keys: one produced "SVGViewer" and the other "prometheus.svg".
function elementName(el: AnyElement): string {
  if (el.type === "custom") {
    return (propName(el) || el.name || "").trim();
  }
  return (el.name ?? propName(el)).trim();
}

// Shared "what is this actually pointing at" signal, cheapest-truthy-wins:
// name beats url beats path beats id. Name is the most stable signal across
// the two delivery channels (step.elements vs the separate elementState
// atom) — the same logical asset can arrive with a resolved url on one side
// and only an id to resolve later on the other, but the filename tends to
// match on both.
function resourceSignature(el: AnyElement): string {
  return (elementName(el) || el.url || el.path || elementId(el) || "").toLowerCase();
}

function imageDuplicateKey(el: AnyElement): string {
  return resourceSignature(el);
}

// NOTE: previously prioritized `id` first here. Switched to content-first
// (via resourceSignature) because two copies of the same element pushed
// through step.elements and elementState don't reliably share an id — see
// the SVG double-render case. If this ever collapses two genuinely
// different elements attached to the same message that happen to share a
// name (rare — would require one agent turn emitting two same-named
// elements of the same type), revisit with a content hash instead.
function elementDuplicateKey(el: AnyElement): string {
  return `${el.type}:${resourceSignature(el)}`;
}

function dedupeElements(elements: AnyElement[]): AnyElement[] {
  const previewImageKeys = new Set(
    elements
      .filter((el) => el.type !== "file" && classifyElement(el) === "image")
      .map(imageDuplicateKey)
      .filter(Boolean),
  );
  const seen = new Set<string>();

  return elements.filter((el) => {
    if (
      el.type === "file" &&
      classifyElement(el) === "image" &&
      previewImageKeys.has(imageDuplicateKey(el))
    ) {
      return false;
    }

    const key = elementDuplicateKey(el);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function ElementList({
  elements,
  onSend,
}: {
  elements?: AnyElement[];
  onSend?: (text: string) => void;
}) {
  if (!elements?.length) return null;
  const uniqueElements = dedupeElements(elements);
  if (!uniqueElements.length) return null;

  return (
    <div className="mt-2 space-y-1">
      {uniqueElements.map((el, i) => (
        <ElementRenderer
          key={elementId(el) || elementDuplicateKey(el) || i}
          element={el}
          onSend={onSend}
        />
      ))}
    </div>
  );
}
