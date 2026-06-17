import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff, Layers } from "lucide-react";

type Item = { key: string; label: string };

type SectionData = {
  items: readonly Item[];
  visibility: Record<string, boolean>;
  onToggle: (key: string) => void;
};

type Props = {
  elementItems: readonly Item[];
  elementVisibility: Record<string, boolean>;
  onToggleElement: (key: string) => void;
  equipment?: SectionData;
  pipes?: SectionData;
  disabled?: boolean;
  // Whole-panel open state — driven by viewer width (auto-collapses when narrow)
  defaultOpen?: boolean;
};

const ViewerVisibilityPanel: React.FC<Props> = ({
  elementItems,
  elementVisibility,
  onToggleElement,
  equipment,
  pipes,
  disabled = false,
  defaultOpen = true,
}) => {
  const [panelOpen, setPanelOpen] = useState(defaultOpen);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    elements:  true,
    equipment: true,
    pipes:     true,
  });

  // Follow width-driven changes (e.g. chat column ↔ full-width view)
  useEffect(() => { setPanelOpen(defaultOpen); }, [defaultOpen]);

  const toggleSection = (id: string) =>
    setOpenSections((prev) => ({ ...prev, [id]: !prev[id] }));

  // Collapsed state — matches the control panel header style so both panels
  // look like they belong to the same family when minimised.
  if (!panelOpen) {
    return (
      <div className="absolute top-2 left-2 z-20 w-64 bg-base-100/95 backdrop-blur rounded-md shadow-lg border border-base-300 overflow-hidden">
        <button
          type="button"
          aria-label="Expand visibility panel"
          className="w-full flex items-center justify-between px-3 py-2 bg-base-200 hover:bg-base-300 transition-colors"
          onClick={() => setPanelOpen(true)}
        >
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Layers size={14} />
            Visibility
          </div>
          <ChevronRight size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="absolute top-2 left-2 z-20 w-64 max-h-[calc(100%-1rem)] flex flex-col bg-base-100/95 backdrop-blur rounded-md shadow-lg border border-base-300 overflow-hidden">

      {/* Panel header */}
      <button
        type="button"
        aria-label="Collapse visibility panel"
        className="w-full flex items-center justify-between px-3 py-2 bg-base-200 border-b border-base-300 hover:bg-base-300 transition-colors"
        onClick={() => setPanelOpen(false)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Layers size={14} />
          Visibility
        </div>
        <ChevronDown size={14} />
      </button>

      <div className="flex-1 overflow-y-auto">
        <Section
          id="elements"
          title="Building Elements"
          items={elementItems}
          visibility={elementVisibility}
          isOpen={openSections.elements}
          onToggleOpen={() => toggleSection("elements")}
          onToggleItem={onToggleElement}
          disabled={disabled}
        />
        {equipment && (
          <Section
            id="equipment"
            title="Equipment"
            items={equipment.items}
            visibility={equipment.visibility}
            isOpen={openSections.equipment}
            onToggleOpen={() => toggleSection("equipment")}
            onToggleItem={equipment.onToggle}
            disabled={disabled}
          />
        )}
        {pipes && (
          <Section
            id="pipes"
            title="Pipes"
            items={pipes.items}
            visibility={pipes.visibility}
            isOpen={openSections.pipes}
            onToggleOpen={() => toggleSection("pipes")}
            onToggleItem={pipes.onToggle}
            disabled={disabled}
          />
        )}
      </div>
    </div>
  );
};

type SectionProps = {
  id: string;
  title: string;
  items: readonly Item[];
  visibility: Record<string, boolean>;
  isOpen: boolean;
  onToggleOpen: () => void;
  onToggleItem: (key: string) => void;
  disabled?: boolean;
};

const Section: React.FC<SectionProps> = ({
  title,
  items,
  visibility,
  isOpen,
  onToggleOpen,
  onToggleItem,
  disabled,
}) => (
  <div className="border-b border-base-300 last:border-b-0">
    <button
      type="button"
      className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-base-content/70 hover:bg-base-200"
      onClick={onToggleOpen}
    >
      <span>{title}</span>
      {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
    </button>
    {isOpen && (
      items.length === 0 ? (
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
      )
    )}
  </div>
);

export default ViewerVisibilityPanel;
