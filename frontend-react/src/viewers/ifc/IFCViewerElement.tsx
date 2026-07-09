/**
 * Renders the `IFCViewer` Chainlit custom element using the native ThatOpen
 * (@thatopen/components) engine — ported from the Alchemy standalone viewer.
 *
 * The backend (frontend/ Chainlit API) emits this element with props:
 *   { datasetId, fileUrl: "/public/ifc-data/{id}/{file}.ifc", filename, height }
 * (see frontend/components/ifc_integration.py). `fileUrl` is a static path on
 * the API origin; in dev it's proxied via the `/public` rule in vite.config.ts.
 */

import { useEffect, useRef, useState } from "react";
import "./ifc.css";
import IfcViewer, { IFCViewerHandles } from "./IFCViewer";
import ViewerPanel from "./ViewerPanel";
import { VISIBILITY_TOGGLES } from "./modelViewerTypes";
import type { VisibilityCategory } from "./modelViewerTypes";
import type { ViewerProps } from "@/lib/chainlit/elements";

type IFCProps = {
  fileUrl?: string;
  filename?: string;
  height?: string;
};

type LabeledItem = { key: string; label: string };

const defaultVisibility = (): Record<VisibilityCategory, boolean> =>
  Object.fromEntries(VISIBILITY_TOGGLES.map((t) => [t.key, true])) as Record<VisibilityCategory, boolean>;

export function IFCViewerElement({ element }: ViewerProps) {
  const props    = ((element as { props?: IFCProps }).props) ?? {};
  const fileUrl  = props.fileUrl ?? element.url ?? null;
  const filename = props.filename ?? element.name ?? "model.ifc";
  const height   = props.height ?? "560px";

  const ifcViewerRef = useRef<IFCViewerHandles>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-collapse the floating panels when the viewer is narrow. The chat
  // column is capped at max-w-4xl (~896px), so the viewer there is always
  // narrower than this — panels stay collapsed in chat and only expand in a
  // genuinely wide/full-width view. The two panels are ~480px wide combined,
  // so anything under this crowds the model.
  const PANEL_BREAKPOINT = 900;
  const [panelsOpen, setPanelsOpen] = useState(true);

  const [showViewer, setShowViewer] = useState(false);
  const [visibility, setVisibility] = useState<Record<VisibilityCategory, boolean>>(defaultVisibility);
  // Which building-element categories the loaded model actually contains.
  const [presentCategories, setPresentCategories] = useState<VisibilityCategory[]>([]);

  const [equipmentItems,      setEquipmentItems]      = useState<LabeledItem[]>([]);
  const [equipmentVisibility, setEquipmentVisibility] = useState<Record<string, boolean>>({});
  const [pipeItems,           setPipeItems]           = useState<LabeledItem[]>([]);
  const [pipeVisibility,      setPipeVisibility]      = useState<Record<string, boolean>>({});

  // Track viewer width → collapse panels below the breakpoint
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setPanelsOpen(entry.contentRect.width >= PANEL_BREAKPOINT);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Reset local state whenever the model URL changes
  useEffect(() => {
    setShowViewer(false);
    setVisibility(defaultVisibility());
    setPresentCategories([]);
    setEquipmentItems([]);
    setEquipmentVisibility({});
    setPipeItems([]);
    setPipeVisibility({});
  }, [fileUrl]);

  const handleViewerLoad = async () => {
    setShowViewer(true);

    const allCategories = VISIBILITY_TOGGLES.map((t) => t.key);
    const [present, equipment, pipes] = await Promise.all([
      ifcViewerRef.current?.enumerateCategories(allCategories) ?? Promise.resolve<string[]>([]),
      ifcViewerRef.current?.enumerateEquipment() ?? Promise.resolve([]),
      ifcViewerRef.current?.enumeratePipes()     ?? Promise.resolve([]),
    ]).catch((e): [string[], LabeledItem[], LabeledItem[]] => {
      console.error("[IFCViewerElement] enumeration failed", e);
      return [[], [], []];
    });

    setPresentCategories(present as VisibilityCategory[]);
    setEquipmentItems(equipment);
    setEquipmentVisibility(Object.fromEntries(equipment.map((i) => [i.key, true])));
    setPipeItems(pipes);
    setPipeVisibility(Object.fromEntries(pipes.map((i) => [i.key, true])));
  };

  const handleToggleVisibility = (key: VisibilityCategory) => {
    const next = !visibility[key];
    setVisibility((prev) => ({ ...prev, [key]: next }));
    ifcViewerRef.current?.setCategoryVisible(key, next);
  };

  const handleToggleEquipment = (key: string) => {
    const next = !equipmentVisibility[key];
    setEquipmentVisibility((prev) => ({ ...prev, [key]: next }));
    ifcViewerRef.current?.setEquipmentVisible(key, next);
  };

  const handleTogglePipe = (key: string) => {
    const next = !pipeVisibility[key];
    setPipeVisibility((prev) => ({ ...prev, [key]: next }));
    ifcViewerRef.current?.setPipeVisible(key, next);
  };

  if (!fileUrl) {
    return (
      <div className="text-sm text-error/70 bg-error/10 rounded px-3 py-2 my-2">
        No IFC file URL was provided to the viewer.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="ifc-viewer-root relative my-2 w-full max-w-full rounded-lg overflow-hidden border border-base-300 bg-base-200/40"
      style={{ height }}
    >
      {/* Merged viewer panel (visibility + camera + download).
          Expanded in a wide view; collapses to a lone icon in the chat. */}
      {showViewer && (
        <ViewerPanel
          elementItems={VISIBILITY_TOGGLES.filter((t) => presentCategories.includes(t.key))}
          elementVisibility={visibility}
          onToggleElement={(key) => handleToggleVisibility(key as VisibilityCategory)}
          equipment={{
            items: equipmentItems,
            visibility: equipmentVisibility,
            onToggle: handleToggleEquipment,
          }}
          pipes={{
            items: pipeItems,
            visibility: pipeVisibility,
            onToggle: handleTogglePipe,
          }}
          onReset={() => ifcViewerRef.current?.fitToFrame()}
          onTop={()   => ifcViewerRef.current?.setTopView()}
          onFront={() => ifcViewerRef.current?.setFrontView()}
          onSide={()  => ifcViewerRef.current?.setSideView()}
          downloadUrl={fileUrl}
          downloadName={filename}
          defaultOpen={panelsOpen}
        />
      )}

      {/* Loading overlay */}
      {!showViewer && (
        <div className="absolute inset-2 flex flex-col items-center justify-center gap-4 bg-base-100 rounded-md z-10">
          <span className="loading loading-spinner w-24 h-24 text-primary" />
          <p className="text-lg text-base-content/70">Loading 3D viewer…</p>
        </div>
      )}

      {/* Viewer engine — absolutely positioned so the WebGL canvas never
          contributes intrinsic width to the (min-width:auto) flex message
          body; otherwise the renderer↔layout feedback loop grows it forever. */}
      <div className="absolute inset-2 rounded-md overflow-hidden bg-base-100">
        <IfcViewer
          ref={ifcViewerRef}
          modelUrl={fileUrl}
          onLoad={handleViewerLoad}
        />
      </div>
    </div>
  );
}

export default IFCViewerElement;
