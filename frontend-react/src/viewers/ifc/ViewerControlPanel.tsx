import React, { useState } from "react";
import { Video, Download, ChevronDown, ChevronRight } from "lucide-react";

type Props = {
  // Camera
  onReset:  () => void;
  onTop:    () => void;
  onFront:  () => void;
  onSide:   () => void;
  disabled: boolean;

  // Download
  downloadUrl?: string | null;
  downloadName?: string;
};

const ViewerControlPanel: React.FC<Props> = ({
  onReset, onTop, onFront, onSide, disabled,
  downloadUrl, downloadName = "model.ifc",
}) => {
  const [cameraOpen,   setCameraOpen]   = useState(true);
  const [downloadOpen, setDownloadOpen] = useState(true);

  return (
    <div className="absolute top-2 right-2 z-20 w-56 max-h-[calc(100%-1rem)] flex flex-col bg-base-100/95 backdrop-blur rounded-md shadow-lg border border-base-300 overflow-hidden">

      {/* ── Camera section ── */}
      <button
        type="button"
        aria-label="Toggle camera controls"
        className="w-full flex items-center justify-between px-3 py-2 bg-base-200 border-b border-base-300 hover:bg-base-300 transition-colors"
        onClick={() => setCameraOpen((o) => !o)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Video size={14} />
          Camera
        </div>
        {cameraOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {cameraOpen && (
        <div className="border-b border-base-300">
          <div className="grid grid-cols-2 gap-1 p-2">
            <button type="button" className="btn btn-primary btn-xs col-span-2" aria-label="Reset view" onClick={onReset} disabled={disabled}>Reset View</button>
            <button type="button" className="btn btn-ghost btn-xs bg-base-300" aria-label="Top view" onClick={onTop} disabled={disabled}>Top</button>
            <button type="button" className="btn btn-ghost btn-xs bg-base-300" aria-label="Front view" onClick={onFront} disabled={disabled}>Front</button>
            <button type="button" className="btn btn-ghost btn-xs col-span-2 bg-base-300" aria-label="Side view" onClick={onSide} disabled={disabled}>Side</button>
          </div>
        </div>
      )}

      {/* ── Download section ── */}
      <button
        type="button"
        aria-label="Toggle download options"
        className="w-full flex items-center justify-between px-3 py-2 bg-base-200 border-b border-base-300 hover:bg-base-300 transition-colors"
        onClick={() => setDownloadOpen((o) => !o)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Download size={14} />
          Download
        </div>
        {downloadOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {downloadOpen && (
        <div className="flex flex-col gap-1 p-2">
          <a
            href={downloadUrl ?? undefined}
            download={downloadName}
            aria-label="Download IFC"
            className={`btn btn-ghost btn-xs justify-start bg-base-300 ${downloadUrl ? "" : "btn-disabled pointer-events-none opacity-50"}`}
          >
            <Download size={13} />
            IFC
          </a>
        </div>
      )}

    </div>
  );
};

export default ViewerControlPanel;
