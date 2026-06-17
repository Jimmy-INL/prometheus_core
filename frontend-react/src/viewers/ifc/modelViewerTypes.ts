// Visibility toggle definition — category key must match
// IFCViewerEngine.CATEGORY_IFC_CLASSES / CATEGORY_NAME_PATTERNS.
export const VISIBILITY_TOGGLES = [
  { key: "walls",   label: "Walls" },
  { key: "columns", label: "Columns" },
  { key: "roofs",   label: "Roof" },
  { key: "beams",   label: "Beams" },
] as const;

export type VisibilityCategory = typeof VISIBILITY_TOGGLES[number]["key"];
