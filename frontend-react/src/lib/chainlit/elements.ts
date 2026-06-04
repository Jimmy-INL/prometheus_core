/**
 * src/lib/chainlit/elements.ts
 *
 * Classifies Chainlit IElement objects and holds the viewer registry.
 *
 * ADDING A VIEWER
 * ───────────────
 * 1. Import your component below
 * 2. Swap null → YourComponent in VIEWER_REGISTRY
 * Done. ElementRenderer handles the rest.
 */

import type { ComponentType } from "react";
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
  | "exodus"         // ExodusViewer custom element
  | "mermaid"        // Mermaid custom element
  | "thermal"        // ThermalAnalysis custom element
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

export function classifyElement(el: AnyElement): ElementKind {
  const type = el.type ?? "";

  if (type === "custom") {
    switch (el.name) {
      case "IFCViewer":           return "ifc";
      case "ExodusViewer":        return "exodus";
      case "CollapsibleJson":     return "json";
      case "FollowUpSuggestions": return "suggestions";
      case "PlanViewer":          return "plan_viewer";
      case "DynamicForm":         return "dynamic_form";
      case "Mermaid":             return "mermaid";
      case "ThermalAnalysis":     return "thermal";
      default:                    return "unknown";
    }
  }

  if (type === "pdf")   return "pdf";
  if (type === "file")  return "file";
  if (type === "image") return "image";

  return "unknown";
}

// ---------------------------------------------------------------------------
// Registry — swap null → component as you build each viewer
// ---------------------------------------------------------------------------

import { DynamicFormElement }                from "../../viewers/DynamicFormElement";
// import { IFCViewerElement }            from "../../viewers/IFCViewerElement";
// import { ExodusViewerElement }         from "../../viewers/ExodusViewerElement";
// import { PdfViewerElement }            from "../../viewers/PdfViewerElement";
// import { FileDownloadElement }         from "../../viewers/FileDownloadElement";
// import { ImageViewerElement }          from "../../viewers/ImageViewerElement";
// import { CollapsibleJsonElement }      from "../../viewers/CollapsibleJsonElement";
// import { FollowUpSuggestionsElement }  from "../../viewers/FollowUpSuggestionsElement";
// import { PlanViewerElement }           from "../../viewers/PlanViewerElement";
// import { MermaidElement }              from "../../viewers/MermaidElement";
// import { ThermalAnalysisElement }      from "../../viewers/ThermalAnalysisElement";

export const VIEWER_REGISTRY: Partial<Record<ElementKind, ViewerComponent | null>> = {
  ifc:          null,  // → IFCViewerElement
  exodus:       null,  // → ExodusViewerElement
  pdf:          null,  // → PdfViewerElement
  file:         null,  // → FileDownloadElement
  image:        null,  // → ImageViewerElement
  json:         null,  // → CollapsibleJsonElement
  suggestions:  null,  // → FollowUpSuggestionsElement  (needs onSend)
  plan_viewer:  null,  // → PlanViewerElement
  dynamic_form: DynamicFormElement,
  mermaid:      null,  // → MermaidElement
  thermal:      null,  // → ThermalAnalysisElement
  unknown:      null,
};
