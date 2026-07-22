/**
 * Classifies Chainlit IElement objects and holds the viewer registry.
 *
 * ADDING A VIEWER
 * ───────────────
 * 1. Import your component below
 * 2. Swap null → YourComponent in VIEWER_REGISTRY
 * Done. ElementRenderer handles the rest.
 */

import { lazy, type ComponentType } from "react";
import type { IElement } from "@chainlit/react-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ElementKind =
  | "pdf"
  | "file"
  | "image"
  | "json"           // CollapsibleJson custom element
  | "suggestions"    // FollowUpSuggestions custom element
  | "plan_viewer"    // PlanViewer custom element
  | "dynamic_form"   // DynamicForm custom element (ask_form path)
  | "ifc"            // IFCViewer custom element
  | "mesh"           // MeshViewer custom element — shared by Exodus and STL
  | "mermaid"        // Mermaid custom element
  | "thermal"        // ThermalAnalysisViewer custom element
  | "unknown";

export type AnyElement = IElement & {
  type: string;
  name?: string;
  url?: string;
  path?: string;
  mime?: string;
  props?: Record<string, unknown>;
};

export interface ViewerProps {
  element: AnyElement;
  onSend?: (text: string) => void;
}

export type ViewerComponent = ComponentType<ViewerProps>;

// ---------------------------------------------------------------------------
// Classifier
// ---------------------------------------------------------------------------

const IMAGE_MIME_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/svg+xml",
]);

const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".svg"];

function normalizeMime(mime?: string): string {
  return (mime ?? "").split(";", 1)[0].trim().toLowerCase();
}

function isImageFile(el: AnyElement): boolean {
  const mime = normalizeMime(el.mime);
  if (IMAGE_MIME_TYPES.has(mime)) return true;

  const name = (el.name ?? el.path ?? el.url ?? "").toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function classifyElement(el: AnyElement): ElementKind {
  const type = el.type ?? "";

  if (type === "custom") {
    switch (el.name) {
      case "IFCViewer":           return "ifc";
      // Confirmed: backend emits this custom element as "MeshViewer" for BOTH
      // Exodus and STL artifacts (components/stl_integration.py /
      // exodus_integration.py — both route through MeshDataset.to_chainlit_element()
      // using the shared COMPONENT_NAME="MeshViewer"). There is no separate
      // "ExodusViewer" name on the wire.
      case "MeshViewer":          return "mesh";
      case "CollapsibleJson":     return "json";
      case "FollowUpSuggestions": return "suggestions";
      case "PlanViewer":          return "plan_viewer";
      case "DynamicForm":         return "dynamic_form";
      case "MermaidViewer":       return "mermaid";
      // Backend COMPONENT_NAME is "ThermalAnalysisViewer", not "ThermalAnalysis"
      // (see prometheus.thermal_analysis.result.v1 plugin __init__.py).
      case "ThermalAnalysisViewer": return "thermal";
      case "SVGViewer":           return "image";
      default:                    return "unknown";
    }
  }

  if (type === "pdf")   return "pdf";
  if (type === "file")  return isImageFile(el) ? "image" : "file";
  if (type === "image") return "image";

  return "unknown";
}

// ---------------------------------------------------------------------------
// Registry — swap null → component as you build each viewer
// ---------------------------------------------------------------------------

import { DynamicFormElement }                from "../../viewers/DynamicFormElement";
// prod: lazy — @thatopen/components + three (~5 MB) stay in their own chunk,
//   fetched only when an IFC element renders. ElementRenderer wraps every
//   viewer in <Suspense>.
// dev: eager-resolve the same dynamic import (top-level await) so there's no
//   Suspense boundary to re-suspend on HMR. Re-suspending would remount and
//   re-initialize the heavy WebGL/WASM engine, whose ThatOpen worker doesn't
//   cleanly re-init mid-session → perpetual "Loading…" spinner.
// Both branches use import() (no static import), so prod DCEs the dev branch
// and the IFC chunk split is preserved (verified in build).
const IFCViewerElement = import.meta.env.DEV
  ? (await import("../../viewers/ifc/IFCViewerElement")).default
  : lazy(() => import("../../viewers/ifc/IFCViewerElement"));
// @kitware/vtk.js is a comparably heavy dependency (bundle-only builds of vtk.js
// itself run well over 1 MB) — same lazy-chunk / dev-HMR reasoning as IFC above.
// vtk.js's own render-window lifecycle isn't WASM-worker-based like ThatOpen's,
// so re-init on HMR is less fraught, but keeping the pattern identical avoids
// having two different loading conventions for the two heaviest viewers.
//
// Shared by STL and Exodus (both emit COMPONENT_NAME="MeshViewer" — see
// classifyElement above). Known pipeline limitations, not blockers to
// shipping: the manifest's `representation` field ("surface" | "volume") is
// never read, so everything renders as surface polydata; and block
// visibility can't be toggled post-load since block selection happens once,
// backend-side, at VTP conversion time (no per-cell block ID in the VTP
// output). Both require a backend/pipeline change to fix, not a frontend one.
const MeshViewerElement = import.meta.env.DEV
  ? (await import("../../viewers/mesh/MeshViewerElement")).default
  : lazy(() => import("../../viewers/mesh/MeshViewerElement"));
// Lazy — the mermaid npm package plus its parser (~500KB+) shouldn't sit in
// the main chunk when most sessions won't render a diagram. Unlike IFC/Mesh,
// mermaid's render lifecycle is stateless per-call (no persistent WASM
// worker, no long-lived render window), so re-suspending on HMR is harmless
// here — no DEV/prod branch needed.
const MermaidElement = lazy(() => import("../../viewers/MermaidElement"));
import { PdfViewerElement }                from "../../viewers/PdfViewerElement";
import { FileDownloadElement }             from "../../viewers/FileDownloadElement";
import { ImageViewerElement }              from "../../viewers/ImageViewerElement";
import { JSONViewer }                      from "../../viewers/JSONViewer";
import { FollowUpSuggestionsElement }      from "../../viewers/FollowUpSuggestionsElement";
import { PlanViewerElement }               from "../../viewers/PlanViewerElement";
import { ThermalAnalysisElement }          from "../../viewers/ThermalAnalysisElement";

export const VIEWER_REGISTRY: Partial<Record<ElementKind, ViewerComponent | null>> = {
  ifc:          IFCViewerElement,
  mesh:         MeshViewerElement, // wired and live — see notes above
  pdf:          PdfViewerElement,
  file:         FileDownloadElement,
  image:        ImageViewerElement,
  json:         JSONViewer,
  suggestions:  FollowUpSuggestionsElement,
  plan_viewer:  PlanViewerElement,
  dynamic_form: DynamicFormElement,
  mermaid:      MermaidElement,
  thermal:      ThermalAnalysisElement,
  unknown:      null,
};
