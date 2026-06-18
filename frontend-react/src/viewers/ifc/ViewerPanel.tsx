import React, { useEffect, useState } from "react";
import {
  ChevronDown, ChevronRight, Eye, EyeOff,
  Video, Download, SlidersHorizontal, Minimize2,
} from "lucide-react";

type Item = { key: string; label: string };

export type SectionData = {
  items: readonly Item[];
  visibility: Record<string, boolean>;
  onToggle: (key: string) => void;
};

type Props = {
  // Visibility
  elementItems: readonly Item[];
  elementVisibility: Record<string, boolean>;
  onToggleElement: (key: string) => void;
  equipment?: SectionData;
  pipes?: SectionData;

  // Camera
  onReset: () => void;
  onTop:   () => void;
  onFront: () => void;
  onSide:  () => void;

  // Download
  downloadUrl?: string | null;
  downloadName?: string;

  disabled?: boolean;
  // Whole-panel open state — driven by viewer width. Expanded in a wide view,
  // collapsed to a lone icon in the narrow chat column.
  defaultOpen?: boolean;
};

const ViewerPanel: React.FC<Props> = ({
  elementItems, elementVisibility, onToggleElement, equipment, pipes,
  onReset, onTop, onFront, onSide,
  downloadUrl, downloadName = "model.ifc",
  disabled = false,
  defaultOpen = true,
}) => {
  const [open, setOpen] = useState(defaultOpen);
  const [sections, setSections] = useState<Record<string, boolean>>({
    elements: true, equipment: true, pipes: true, camera: true, download: true,
  });

  // Follow width-driven changes (chat ↔ full-width view)
  useEffect(() => { setOpen(defaultOpen); }, [defaultOpen]);

  const toggleSection = (id: string) =>
    setSections((prev) => ({ ...prev, [id]: !prev[id] }));

  // Fully collapsed — just an icon.
  if (!open) {
    return (
      <button
        type="button"
        aria-label="Open viewer panel"
        className="absolute top-2 left-2 z-20 flex items-center justify-center w-9 h-9 bg-base-100/95 backdrop-blur rounded-md shadow-lg border border-base-300 hover:bg-base-200 transition-colors"
        onClick={() => setOpen(true)}
      >
        <SlidersHorizontal size={16} />
      </button>
    );
  }

  return (
    <div className="absolute top-2 left-2 z-20 w-64 max-h-[calc(100%-1rem)] flex flex-col bg-base-100/95 backdrop-blur rounded-md shadow-lg border border-base-300 overflow-hidden">

      {/* Panel header — collapse to icon */}
      <button
        type="button"
        aria-label="Collapse viewer panel"
        className="w-full flex items-center justify-between px-3 py-2 bg-base-200 border-b border-base-300 hover:bg-base-300 transition-colors"
        onClick={() => setOpen(false)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold">
          <SlidersHorizontal size={14} />
          Viewer
        </div>
        <Minimize2 size={14} />
      </button>

      <div className="flex-1 overflow-y-auto">
        <ListSection
          title="Building Elements"
          items={elementItems}
          visibility={elementVisibility}
          isOpen={sections.elements}
          onToggleOpen={() => toggleSection("elements")}
          onToggleItem={onToggleElement}
          disabled={disabled}
        />
        {equipment && (
          <ListSection
            title="Equipment"
            items={equipment.items}
            visibility={equipment.visibility}
            isOpen={sections.equipment}
            onToggleOpen={() => toggleSection("equipment")}
            onToggleItem={equipment.onToggle}
            disabled={disabled}
          />
        )}
        {pipes && (
          <ListSection
            title="Pipes"
            items={pipes.items}
            visibility={pipes.visibility}
            isOpen={sections.pipes}
            onToggleOpen={() => toggleSection("pipes")}
            onToggleItem={pipes.onToggle}
            disabled={disabled}
          />
        )}

        {/* Camera */}
        <Section title="Camera" icon={<Video size={12} />} isOpen={sections.camera} onToggleOpen={() => toggleSection("camera")}>
          <div className="grid grid-cols-2 gap-1 p-2">
            <button type="button" className="btn btn-primary btn-xs col-span-2" aria-label="Reset view" onClick={onReset} disabled={disabled}>Reset View</button>
            <button type="button" className="btn btn-ghost btn-xs bg-base-300" aria-label="Top view" onClick={onTop} disabled={disabled}>Top</button>
            <button type="button" className="btn btn-ghost btn-xs bg-base-300" aria-label="Front view" onClick={onFront} disabled={disabled}>Front</button>
            <button type="button" className="btn btn-ghost btn-xs col-span-2 bg-base-300" aria-label="Side view" onClick={onSide} disabled={disabled}>Side</button>
          </div>
        </Section>

        {/* Download */}
        <Section title="Download" icon={<Download size={12} />} isOpen={sections.download} onToggleOpen={() => toggleSection("download")}>
          <div className="p-2">
            <a
              href={downloadUrl ?? undefined}
              download={downloadName}
              aria-label="Download IFC"
              className={`btn btn-ghost btn-xs justify-start bg-base-300 w-full ${downloadUrl ? "" : "btn-disabled pointer-events-none opacity-50"}`}
            >
              <Download size={13} />
              IFC
            </a>
          </div>
        </Section>
      </div>
    </div>
  );
};

// ── Collapsible section wrapper (shared by list + control sections) ─────────

type SectionProps = {
  title: string;
  icon?: React.ReactNode;
  isOpen: boolean;
  onToggleOpen: () => void;
  children: React.ReactNode;
};

const Section: React.FC<SectionProps> = ({ title, icon, isOpen, onToggleOpen, children }) => (
  <div className="border-b border-base-300 last:border-b-0">
    <button
      type="button"
      className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-base-content/70 hover:bg-base-200"
      onClick={onToggleOpen}
    >
      <span className="flex items-center gap-1.5">{icon}{title}</span>
      {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
    </button>
    {isOpen && children}
  </div>
);

// ── Visibility item list ────────────────────────────────────────────────────

type ListSectionProps = {
  title: string;
  items: readonly Item[];
  visibility: Record<string, boolean>;
  isOpen: boolean;
  onToggleOpen: () => void;
  onToggleItem: (key: string) => void;
  disabled?: boolean;
};

const ListSection: React.FC<ListSectionProps> = ({
  title, items, visibility, isOpen, onToggleOpen, onToggleItem, disabled,
}) => (
  <Section title={title} isOpen={isOpen} onToggleOpen={onToggleOpen}>
    {items.length === 0 ? (
      <p className="px-3 py-2 text-xs text-base-content/40 italic">None</p>
    ) : (
      <ul className="py-1">
        {items.map((item) => {
          const on = visibility[item.key];
          return (
            <li key={item.key}>
              <button
                type="button"
                disabled={disabled}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-base-200 text-left disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => onToggleItem(item.key)}
              >
                {on
                  ? <Eye size={14} className="text-primary shrink-0" />
                  : <EyeOff size={14} className="text-base-content/40 shrink-0" />}
                <span className={on ? "" : "text-base-content/40 line-through"}>
                  {item.label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    )}
  </Section>
);

export default ViewerPanel;
