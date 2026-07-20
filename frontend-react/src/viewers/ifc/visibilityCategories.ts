// Category key must match IFCViewerEngine.CATEGORY_IFC_CLASSES / CATEGORY_NAME_PATTERNS.
export const VISIBILITY_TOGGLES = [
  { key: "walls",   label: "Walls" },
  { key: "floors",  label: "Floors" },
  { key: "columns", label: "Columns" },
  { key: "beams",   label: "Beams" },
  { key: "doors",   label: "Doors" },
  { key: "windows", label: "Windows" },
  { key: "roofs",   label: "Roof" },
] as const;

export type VisibilityCategory = typeof VISIBILITY_TOGGLES[number]["key"];
