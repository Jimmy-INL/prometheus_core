/**
 * src/viewers/IFCViewerElement.tsx
 *
 * Renders the `IFCViewer` Chainlit custom element using the native ThatOpen
 * (@thatopen/components) engine — ported from the Alchemy standalone viewer.
 *
 * The backend (frontend/ Chainlit API) emits this element with props:
 *   { datasetId, fileUrl: "/public/ifc-data/{id}/{file}.ifc", filename, height }
 * (see frontend/components/ifc_integration.py). `fileUrl` is a static path on
 * the API origin; in dev it's proxied via the `/public` rule in vite.config.ts.
 */

import { useEffect, useRef, useState } from "react";
import IfcViewer, { IFCViewerHandles } from "./IFCViewer";
import ViewerVisibilityPanel from "./ViewerVisibilityPanel";
import ViewerControlPanel from "./ViewerControlPanel";
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

  // Auto-collapse the floating panels when the viewer is narrow (e.g. embedded
  // in the chat column). They expand automatically in a wider/full-width view.
  const PANEL_BREAKPOINT = 640;
  const [panelsOpen, setPanelsOpen] = useState(true);

  const [showViewer, setShowViewer] = useState(false);
  const [visibility, setVisibility] = useState<Record<VisibilityCategory, boolean>>(defaultVisibility);

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
    setEquipmentItems([]);
    setEquipmentVisibility({});
    setPipeItems([]);
    setPipeVisibility({});
  }, [fileUrl]);

  const handleViewerLoad = async () => {
    setShowViewer(true);

    const [equipment, pipes] = await Promise.all([
      ifcViewerRef.current?.enumerateEquipment() ?? Promise.resolve([]),
      ifcViewerRef.current?.enumeratePipes()     ?? Promise.resolve([]),
    ]).catch((e): [LabeledItem[], LabeledItem[]] => {
      console.error("[IFCViewerElement] enumeration failed", e);
      return [[], []];
    });

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
      className="relative my-2 rounded-lg overflow-hidden border border-base-300 bg-base-200/40"
      style={{ height }}
    >
      {/* Top-left: visibility panel */}
      {showViewer && (
        <ViewerVisibilityPanel
          elementItems={VISIBILITY_TOGGLES}
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
          defaultOpen={panelsOpen}
        />
      )}

      {/* Top-right: camera + download panel */}
      {showViewer && (
        <ViewerControlPanel
          onReset={() => ifcViewerRef.current?.fitToFrame()}
          onTop={()   => ifcViewerRef.current?.setTopView()}
          onFront={() => ifcViewerRef.current?.setFrontView()}
          onSide={()  => ifcViewerRef.current?.setSideView()}
          disabled={!showViewer}
          downloadUrl={fileUrl}
          downloadName={filename}
          defaultOpen={panelsOpen}
        />
      )}

      {/* Loading overlay */}
      {!showViewer && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-base-100 z-10">
          <span className="loading loading-spinner w-24 h-24 text-primary" />
          <p className="text-lg text-base-content/70">Loading 3D viewer…</p>
        </div>
      )}

      {/* Viewer engine */}
      <div className="w-full h-full">
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
