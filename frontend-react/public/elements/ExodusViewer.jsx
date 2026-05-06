import { useEffect, useRef, useState, useCallback, useMemo } from "react";

/**
 * Color presets for the viewer.
 */
const COLOR_PRESETS = {
  coolToWarm: [
    [0, 0.231, 0.298, 0.753],
    [0.5, 0.865, 0.865, 0.865],
    [1, 0.706, 0.016, 0.149],
  ],
  viridis: [
    [0, 0.267, 0.004, 0.329],
    [0.25, 0.282, 0.141, 0.458],
    [0.5, 0.127, 0.566, 0.551],
    [0.75, 0.369, 0.788, 0.384],
    [1, 0.993, 0.906, 0.144],
  ],
  plasma: [
    [0, 0.05, 0.03, 0.528],
    [0.25, 0.416, 0.09, 0.633],
    [0.5, 0.797, 0.21, 0.471],
    [0.75, 0.973, 0.58, 0.254],
    [1, 0.94, 0.975, 0.131],
  ],
  rainbow: [
    [0, 0, 0, 1],
    [0.25, 0, 1, 1],
    [0.5, 0, 1, 0],
    [0.75, 1, 1, 0],
    [1, 1, 0, 0],
  ],
  grayscale: [
    [0, 0, 0, 0],
    [1, 1, 1, 1],
  ],
};

const PRESET_LABELS = {
  coolToWarm: "Cool to Warm",
  viridis: "Viridis",
  plasma: "Plasma",
  rainbow: "Rainbow",
  grayscale: "Grayscale",
};

// SVG Icons as components
const Icons = {
  Play: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M8 5v14l11-7z" />
    </svg>
  ),
  Pause: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
    </svg>
  ),
  SkipBack: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
    </svg>
  ),
  SkipForward: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
    </svg>
  ),
  Reset: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" />
    </svg>
  ),
  Fullscreen: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
    </svg>
  ),
  ExitFullscreen: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
    </svg>
  ),
  ChevronDown: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
      <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z" />
    </svg>
  ),
  ChevronUp: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
      <path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z" />
    </svg>
  ),
};

/**
 * Hook to detect current theme (dark or light mode)
 */
function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    // Check for Chainlit's dark mode class or data attribute
    if (typeof document !== "undefined") {
      const html = document.documentElement;
      const body = document.body;
      // Chainlit uses 'dark' class on html element
      if (html.classList.contains("dark")) return true;
      if (body.classList.contains("dark")) return true;
      // Also check data-theme attribute
      if (html.getAttribute("data-theme") === "dark") return true;
      // Fallback to system preference
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return true;
      }
    }
    return true; // Default to dark
  });

  useEffect(() => {
    // Watch for theme changes via MutationObserver
    const observer = new MutationObserver(() => {
      const html = document.documentElement;
      const body = document.body;
      const darkMode =
        html.classList.contains("dark") ||
        body.classList.contains("dark") ||
        html.getAttribute("data-theme") === "dark";
      setIsDark(darkMode);
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });

    // Also watch for system preference changes
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e) => {
      // Only use system preference if no explicit class is set
      const html = document.documentElement;
      if (!html.classList.contains("dark") && !html.classList.contains("light")) {
        setIsDark(e.matches);
      }
    };
    mediaQuery.addEventListener("change", handleChange);

    return () => {
      observer.disconnect();
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, []);

  return isDark;
}

/**
 * Generate theme-aware styles
 */
function getStyles(isDark) {
  const colors = isDark
    ? {
        // Dark theme colors
        bg: "linear-gradient(180deg, rgba(30,30,40,0.95) 0%, rgba(20,20,30,0.98) 100%)",
        bgSolid: "#1e1e28",
        border: "rgba(255,255,255,0.1)",
        borderLight: "rgba(255,255,255,0.08)",
        borderLighter: "rgba(255,255,255,0.05)",
        text: "rgba(255,255,255,0.9)",
        textMuted: "rgba(255,255,255,0.7)",
        textDim: "rgba(255,255,255,0.5)",
        textDimmer: "rgba(255,255,255,0.4)",
        textDimmest: "rgba(255,255,255,0.3)",
        canvas: "#14141e",
        headerBg: "rgba(255,255,255,0.02)",
        controlBg: "rgba(255,255,255,0.08)",
        controlBorder: "rgba(255,255,255,0.12)",
        controlBgHover: "rgba(255,255,255,0.06)",
        pickInfoBg: "rgba(0,0,0,0.8)",
        pickValue: "rgb(165,243,252)",
        colorbarBg: "rgba(0,0,0,0.2)",
        badgeBg: "rgba(99,102,241,0.2)",
        badgeText: "rgb(165,180,252)",
        buttonActiveBg: "rgba(99,102,241,0.9)",
        buttonActiveBorder: "rgba(99,102,241,1)",
        expandBg: "rgba(255,255,255,0.03)",
        shadow: "0 4px 24px rgba(0,0,0,0.3)",
        dropdownArrow: "%23888",
        vtkBg: [0.08, 0.08, 0.12],
      }
    : {
        // Light theme colors
        bg: "linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,249,250,0.98) 100%)",
        bgSolid: "#ffffff",
        border: "rgba(0,0,0,0.12)",
        borderLight: "rgba(0,0,0,0.08)",
        borderLighter: "rgba(0,0,0,0.05)",
        text: "rgba(0,0,0,0.87)",
        textMuted: "rgba(0,0,0,0.7)",
        textDim: "rgba(0,0,0,0.5)",
        textDimmer: "rgba(0,0,0,0.4)",
        textDimmest: "rgba(0,0,0,0.3)",
        canvas: "#e8e8f0",
        headerBg: "rgba(0,0,0,0.02)",
        controlBg: "rgba(0,0,0,0.05)",
        controlBorder: "rgba(0,0,0,0.12)",
        controlBgHover: "rgba(0,0,0,0.08)",
        pickInfoBg: "rgba(255,255,255,0.95)",
        pickValue: "rgb(37,99,235)",
        colorbarBg: "rgba(0,0,0,0.04)",
        badgeBg: "rgba(99,102,241,0.12)",
        badgeText: "rgb(79,70,229)",
        buttonActiveBg: "rgba(99,102,241,0.9)",
        buttonActiveBorder: "rgba(99,102,241,1)",
        expandBg: "rgba(0,0,0,0.02)",
        shadow: "0 4px 24px rgba(0,0,0,0.08)",
        dropdownArrow: "%23666",
        vtkBg: [0.91, 0.91, 0.94],
      };

  return {
    colors,
    container: {
      width: "100%",
      display: "flex",
      flexDirection: "column",
      gap: "0",
      borderRadius: "12px",
      overflow: "hidden",
      border: `1px solid ${colors.border}`,
      background: colors.bg,
      boxShadow: colors.shadow,
    },
    containerFullscreen: {
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: "100vw",
      height: "100vh",
      borderRadius: 0,
      zIndex: 9999,
      display: "flex",
      flexDirection: "column",
      background: colors.bgSolid,
    },
    header: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "10px 16px",
      borderBottom: `1px solid ${colors.borderLight}`,
      background: colors.headerBg,
    },
    title: {
      fontSize: "13px",
      fontWeight: "500",
      color: colors.text,
      display: "flex",
      alignItems: "center",
      gap: "8px",
    },
    badge: {
      fontSize: "10px",
      padding: "2px 8px",
      borderRadius: "10px",
      background: colors.badgeBg,
      color: colors.badgeText,
      fontWeight: "500",
    },
    headerButtons: {
      display: "flex",
      alignItems: "center",
      gap: "6px",
    },
    canvasWrapper: {
      position: "relative",
      width: "100%",
      background: colors.canvas,
      overflow: "hidden",
    },
    pickInfo: {
      position: "absolute",
      bottom: "12px",
      left: "12px",
      background: colors.pickInfoBg,
      backdropFilter: "blur(8px)",
      padding: "8px 12px",
      borderRadius: "8px",
      fontSize: "11px",
      color: colors.text,
      display: "flex",
      alignItems: "center",
      gap: "12px",
      border: `1px solid ${colors.border}`,
    },
    pickLabel: {
      color: colors.textDim,
      marginRight: "4px",
    },
    pickValue: {
      fontFamily: "monospace",
      color: colors.pickValue,
    },
    controls: {
      display: "flex",
      flexDirection: "column",
      gap: "0",
      borderTop: `1px solid ${colors.borderLight}`,
    },
    controlSection: {
      padding: "10px 16px",
      borderBottom: `1px solid ${colors.borderLighter}`,
    },
    controlRow: {
      display: "flex",
      alignItems: "center",
      gap: "10px",
      flexWrap: "wrap",
    },
    controlGroup: {
      display: "flex",
      alignItems: "center",
      gap: "8px",
    },
    label: {
      fontSize: "10px",
      color: colors.textDim,
      textTransform: "uppercase",
      letterSpacing: "0.5px",
      fontWeight: "600",
    },
    select: {
      background: colors.controlBg,
      border: `1px solid ${colors.controlBorder}`,
      borderRadius: "6px",
      padding: "5px 26px 5px 10px",
      fontSize: "12px",
      color: colors.text,
      cursor: "pointer",
      outline: "none",
      appearance: "none",
      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='${colors.dropdownArrow}' viewBox='0 0 24 24'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E")`,
      backgroundRepeat: "no-repeat",
      backgroundPosition: "right 4px center",
      backgroundSize: "18px",
    },
    input: {
      background: colors.controlBg,
      border: `1px solid ${colors.controlBorder}`,
      borderRadius: "6px",
      padding: "5px 8px",
      fontSize: "11px",
      color: colors.text,
      width: "72px",
      outline: "none",
      fontFamily: "monospace",
    },
    buttonIcon: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      width: "30px",
      height: "30px",
      padding: "0",
      borderRadius: "6px",
      border: `1px solid ${colors.controlBorder}`,
      background: colors.controlBgHover,
      color: colors.textMuted,
      cursor: "pointer",
      transition: "all 0.15s ease",
    },
    buttonIconActive: {
      background: colors.buttonActiveBg,
      borderColor: colors.buttonActiveBorder,
      color: "white",
    },
    buttonIconSmall: {
      width: "26px",
      height: "26px",
    },
    slider: {
      flex: 1,
      minWidth: "100px",
      height: "6px",
      borderRadius: "3px",
      background: colors.controlBg,
      cursor: "pointer",
      WebkitAppearance: "none",
      appearance: "none",
    },
    timestepDisplay: {
      minWidth: "90px",
      textAlign: "right",
      fontSize: "11px",
      color: colors.textMuted,
      fontFamily: "monospace",
    },
    colorbar: {
      display: "flex",
      flexDirection: "column",
      gap: "4px",
      padding: "10px 16px",
      background: colors.colorbarBg,
    },
    colorbarHeader: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
    },
    colorbarVariable: {
      fontSize: "11px",
      color: colors.text,
      fontWeight: "500",
    },
    colorbarGradient: {
      height: "10px",
      borderRadius: "5px",
      border: `1px solid ${colors.border}`,
    },
    colorbarLabels: {
      display: "flex",
      justifyContent: "space-between",
      fontSize: "9px",
      fontFamily: "monospace",
      color: colors.textDim,
    },
    expandButton: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: "6px",
      padding: "8px 16px",
      background: colors.expandBg,
      border: "none",
      borderTop: `1px solid ${colors.borderLighter}`,
      color: colors.textDim,
      fontSize: "11px",
      cursor: "pointer",
      transition: "all 0.15s ease",
    },
    loading: {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "48px",
      color: colors.textDim,
    },
    error: {
      padding: "16px",
      background: isDark ? "rgba(239,68,68,0.1)" : "rgba(239,68,68,0.08)",
      border: "1px solid rgba(239,68,68,0.3)",
      borderRadius: "8px",
      color: isDark ? "rgb(252,165,165)" : "rgb(185,28,28)",
      fontSize: "13px",
    },
    divider: {
      width: "1px",
      height: "20px",
      background: colors.border,
      margin: "0 4px",
    },
  };
}

function applyColorPreset(lookupTable, presetName) {
  const preset = COLOR_PRESETS[presetName] || COLOR_PRESETS.coolToWarm;
  lookupTable.removeAllPoints();
  for (const [x, r, g, b] of preset) {
    lookupTable.addRGBPoint(x, r, g, b);
  }
}

function getColorbarGradient(presetName) {
  const preset = COLOR_PRESETS[presetName] || COLOR_PRESETS.coolToWarm;
  const stops = preset.map(([pos, r, g, b]) => {
    const color = `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
    return `${color} ${pos * 100}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

/**
 * Colorbar component
 */
function Colorbar({ styles, preset, min, max, variable, compact = false }) {
  const gradient = getColorbarGradient(preset);

  const formatValue = (val) => {
    if (val === undefined || val === null) return "0";
    if (Math.abs(val) < 0.001 || Math.abs(val) > 10000) {
      return val.toExponential(2);
    }
    return val.toFixed(3);
  };

  if (compact) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: "150px" }}>
        <span style={{ fontSize: "9px", color: styles.colors.textDim, fontFamily: "monospace" }}>
          {formatValue(min)}
        </span>
        <div style={{ ...styles.colorbarGradient, background: gradient, flex: 1, height: "8px" }} />
        <span style={{ fontSize: "9px", color: styles.colors.textDim, fontFamily: "monospace" }}>
          {formatValue(max)}
        </span>
      </div>
    );
  }

  return (
    <div style={styles.colorbar}>
      <div style={styles.colorbarHeader}>
        <span style={styles.colorbarVariable}>{variable}</span>
        <span style={{ fontSize: "9px", color: styles.colors.textDimmer }}>
          {PRESET_LABELS[preset]}
        </span>
      </div>
      <div style={{ ...styles.colorbarGradient, background: gradient }} />
      <div style={styles.colorbarLabels}>
        <span>{formatValue(min)}</span>
        <span>{formatValue((min + max) / 2)}</span>
        <span>{formatValue(max)}</span>
      </div>
    </div>
  );
}

/**
 * ExodusViewer - VTK.js based viewer for Exodus II datasets.
 */
export default function ExodusViewer() {
  const containerRef = useRef(null);
  const viewerContainerRef = useRef(null);
  const vtkState = useRef(null);

  const isDark = useTheme();
  const styles = useMemo(() => getStyles(isDark), [isDark]);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentTimestep, setCurrentTimestep] = useState(props.initialTimestep || 0);
  const [currentVariable, setCurrentVariable] = useState(props.initialVariable || null);
  const [colorPreset, setColorPreset] = useState(props.initialColorPreset || "coolToWarm");
  const [scalarRange, setScalarRange] = useState([0, 1]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [pickedInfo, setPickedInfo] = useState(null);
  const [vtkReady, setVtkReady] = useState(!!window.vtk);
  const [expanded, setExpanded] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const playIntervalRef = useRef(null);

  const {
    datasetId,
    baseUrl,
    metadata = {},
    manifest = {},
    height = "450px",
    showControls = true,
    allowPicking = true,
  } = props;

  const numTimesteps = metadata.num_timesteps || 1;
  const timeValues = metadata.time_values || [];
  const files = manifest.files || [];
  const pointVariables = manifest.variables?.point || [];
  const cellVariables = manifest.variables?.cell || [];
  const arrayRanges = manifest.array_ranges || {};

  // Update VTK background when theme changes
  useEffect(() => {
    if (vtkState.current?.renderer) {
      vtkState.current.renderer.setBackground(styles.colors.vtkBg);
      vtkState.current.renderWindow.render();
    }
  }, [isDark, styles.colors.vtkBg]);

  // Fullscreen handling
  const toggleFullscreen = useCallback(() => {
    if (!viewerContainerRef.current) return;

    if (!document.fullscreenElement) {
      viewerContainerRef.current.requestFullscreen().catch((err) => {
        console.error("Failed to enter fullscreen:", err);
      });
    } else {
      document.exitFullscreen();
    }
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
      setTimeout(() => {
        if (vtkState.current?.renderWindow) {
          vtkState.current.renderWindow.render();
        }
      }, 100);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  // Wait for vtk.js
  useEffect(() => {
    if (window.vtk) {
      setVtkReady(true);
      return;
    }
    const handleVtkReady = () => setVtkReady(true);
    window.addEventListener("vtk-ready", handleVtkReady);
    return () => window.removeEventListener("vtk-ready", handleVtkReady);
  }, []);

  // Initialize VTK viewer
  useEffect(() => {
    if (!vtkReady || !containerRef.current) return;

    const vtk = window.vtk;
    if (!vtk) return;

    containerRef.current.innerHTML = "";

    try {
      const fullScreenRenderWindow = vtk.Rendering.Misc.vtkFullScreenRenderWindow.newInstance({
        rootContainer: containerRef.current,
        containerStyle: { width: "100%", height: "100%" },
        background: styles.colors.vtkBg,
      });

      const renderer = fullScreenRenderWindow.getRenderer();
      const renderWindow = fullScreenRenderWindow.getRenderWindow();

      const lookupTable = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
      applyColorPreset(lookupTable, colorPreset);

      const mapper = vtk.Rendering.Core.vtkMapper.newInstance({
        interpolateScalarsBeforeMapping: true,
        useLookupTableScalarRange: true,
      });
      mapper.setLookupTable(lookupTable);

      const actor = vtk.Rendering.Core.vtkActor.newInstance();
      actor.setMapper(mapper);
      actor.getProperty().setEdgeVisibility(false);
      actor.getProperty().setLighting(true);

      const picker = vtk.Rendering.Core.vtkCellPicker.newInstance();
      picker.setPickFromList(1);
      picker.initializePickList();
      picker.addPickList(actor);

      renderer.addActor(actor);

      vtkState.current = {
        fullScreenRenderWindow,
        renderer,
        renderWindow,
        actor,
        mapper,
        lookupTable,
        picker,
        currentPolyData: null,
        currentArrayName: null,
      };

      if (allowPicking) {
        const container = fullScreenRenderWindow.getContainer();
        const handleClick = (event) => {
          const rect = container.getBoundingClientRect();
          const x = event.clientX - rect.left;
          const y = event.clientY - rect.top;
          const dims = [rect.width, rect.height];
          const displayCoord = [x, dims[1] - y, 0];

          picker.pick(displayCoord, renderer);
          const cellId = picker.getCellId();

          if (cellId < 0) {
            setPickedInfo(null);
            return;
          }

          const pickPos = picker.getPickPosition();
          let value = null;

          if (vtkState.current.currentPolyData && vtkState.current.currentArrayName) {
            const polyData = vtkState.current.currentPolyData;
            const arrayName = vtkState.current.currentArrayName;
            const cellArray = polyData.getCellData().getArrayByName(arrayName);
            if (cellArray) {
              const data = cellArray.getData();
              if (cellId < data.length) value = data[cellId];
            }
          }

          setPickedInfo({ position: pickPos, cellId, value });
        };

        container.addEventListener("click", handleClick);
        vtkState.current.cleanupPicking = () => container.removeEventListener("click", handleClick);
      }

      setIsLoading(false);
    } catch (err) {
      console.error("Failed to initialize VTK viewer:", err);
      setError(`Failed to initialize viewer: ${err.message}`);
      setIsLoading(false);
    }

    return () => {
      if (vtkState.current) {
        if (vtkState.current.cleanupPicking) vtkState.current.cleanupPicking();
        if (vtkState.current.fullScreenRenderWindow) {
          try {
            vtkState.current.fullScreenRenderWindow.delete();
          } catch (e) {}
        }
      }
      vtkState.current = null;
    };
  }, [vtkReady, allowPicking]);

  const loadTimestep = useCallback(async (timestepIndex) => {
    if (!vtkState.current || !files.length) return;
    const vtk = window.vtk;
    if (!vtk) return;

    const fileInfo = files.find((f) => f.timestep_index === timestepIndex) || files[timestepIndex];
    if (!fileInfo) return;

    const fileUrl = `${baseUrl}/${fileInfo.filename}`;

    try {
      const response = await fetch(fileUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const buffer = await response.arrayBuffer();
      const reader = vtk.IO.XML.vtkXMLPolyDataReader.newInstance();
      reader.parseAsArrayBuffer(buffer);
      const polyData = reader.getOutputData(0);

      vtkState.current.mapper.setInputData(polyData);
      vtkState.current.currentPolyData = polyData;

      if (currentTimestep === 0 || !vtkState.current.cameraInitialized) {
        vtkState.current.renderer.resetCamera();
        vtkState.current.cameraInitialized = true;
      }

      if (currentVariable) applyVariableColoring(currentVariable);
      vtkState.current.renderWindow.render();
    } catch (err) {
      console.error(`Failed to load timestep ${timestepIndex}:`, err);
      setError(`Failed to load timestep: ${err.message}`);
    }
  }, [baseUrl, files, currentVariable]);

  const applyVariableColoring = useCallback((varName) => {
    if (!vtkState.current || !vtkState.current.currentPolyData) return;

    const polyData = vtkState.current.currentPolyData;
    const mapper = vtkState.current.mapper;
    const lookupTable = vtkState.current.lookupTable;

    const isPointData = pointVariables.includes(varName);
    const isCellData = cellVariables.includes(varName);
    if (!isPointData && !isCellData) return;

    const dataArray = isPointData
      ? polyData.getPointData().getArrayByName(varName)
      : polyData.getCellData().getArrayByName(varName);

    if (!dataArray) return;

    if (isPointData) mapper.setScalarModeToUsePointFieldData();
    else mapper.setScalarModeToUseCellFieldData();

    mapper.setColorByArrayName(varName);
    mapper.setScalarVisibility(true);

    let range = arrayRanges[varName];
    if (!range) range = dataArray.getRange();

    setScalarRange(range);
    lookupTable.setMappingRange(range[0], range[1]);
    lookupTable.updateRange();

    vtkState.current.currentArrayName = varName;
    vtkState.current.renderWindow.render();
  }, [pointVariables, cellVariables, arrayRanges]);

  useEffect(() => {
    if (!isLoading && vtkState.current) loadTimestep(currentTimestep);
  }, [isLoading, loadTimestep]);

  useEffect(() => {
    if (!isLoading && vtkState.current) loadTimestep(currentTimestep);
  }, [currentTimestep, isLoading, loadTimestep]);

  useEffect(() => {
    if (!isLoading && vtkState.current && currentVariable) applyVariableColoring(currentVariable);
  }, [currentVariable, isLoading, applyVariableColoring]);

  useEffect(() => {
    if (!vtkState.current) return;
    applyColorPreset(vtkState.current.lookupTable, colorPreset);
    vtkState.current.lookupTable.setMappingRange(scalarRange[0], scalarRange[1]);
    vtkState.current.lookupTable.updateRange();
    vtkState.current.renderWindow.render();
  }, [colorPreset, scalarRange]);

  useEffect(() => {
    if (isPlaying && numTimesteps > 1) {
      playIntervalRef.current = setInterval(() => {
        setCurrentTimestep((prev) => (prev + 1) % numTimesteps);
      }, 200);
    } else {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
        playIntervalRef.current = null;
      }
    }
    return () => {
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
    };
  }, [isPlaying, numTimesteps]);

  const handleRangeChange = (which, value) => {
    const numVal = parseFloat(value);
    if (isNaN(numVal)) return;
    const newRange = [...scalarRange];
    newRange[which === "min" ? 0 : 1] = numVal;
    setScalarRange(newRange);
    if (vtkState.current) {
      vtkState.current.lookupTable.setMappingRange(newRange[0], newRange[1]);
      vtkState.current.lookupTable.updateRange();
      vtkState.current.renderWindow.render();
    }
  };

  const handleResetCamera = () => {
    if (vtkState.current) {
      vtkState.current.renderer.resetCamera();
      vtkState.current.renderWindow.render();
    }
  };

  if (!vtkReady) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>Loading VTK.js...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={{ padding: "16px" }}>
          <div style={styles.error}>{error}</div>
        </div>
      </div>
    );
  }

  const variableOptions = [
    ...pointVariables.map((v) => ({ value: v, label: v, type: "point" })),
    ...cellVariables.map((v) => ({ value: v, label: v, type: "cell" })),
  ];

  const formatTime = (t) => {
    if (t === undefined) return "";
    return t < 0.001 || t > 1000 ? t.toExponential(2) : t.toFixed(3);
  };

  return (
    <div
      ref={viewerContainerRef}
      style={isFullscreen ? { ...styles.container, ...styles.containerFullscreen } : styles.container}
    >
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.title}>
          <span>Exodus Viewer</span>
          <span style={styles.badge}>{datasetId}</span>
        </div>
        <div style={styles.headerButtons}>
          <button
            style={styles.buttonIcon}
            onClick={handleResetCamera}
            title="Reset Camera"
          >
            <Icons.Reset />
          </button>
          <button
            style={styles.buttonIcon}
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? <Icons.ExitFullscreen /> : <Icons.Fullscreen />}
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div style={{
        ...styles.canvasWrapper,
        height: isFullscreen ? undefined : height,
        flex: isFullscreen ? 1 : undefined,
      }}>
        <div ref={containerRef} style={{ width: "100%", height: isFullscreen ? "100%" : height }} />

        {/* Pick info overlay */}
        {pickedInfo && (
          <div style={styles.pickInfo}>
            <span>
              <span style={styles.pickLabel}>Cell</span>
              <span style={styles.pickValue}>{pickedInfo.cellId}</span>
            </span>
            <span>
              <span style={styles.pickLabel}>Pos</span>
              <span style={styles.pickValue}>
                ({pickedInfo.position.map((p) => p.toFixed(2)).join(", ")})
              </span>
            </span>
            {pickedInfo.value !== null && (
              <span>
                <span style={styles.pickLabel}>Val</span>
                <span style={styles.pickValue}>{pickedInfo.value.toExponential(3)}</span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      {showControls && (
        <div style={styles.controls}>
          {/* Minimal controls - always visible */}
          {(numTimesteps > 1 || (currentVariable && !expanded)) && (
            <div style={styles.controlSection}>
              <div style={styles.controlRow}>
                {/* Play/Pause - only if multiple timesteps */}
                {numTimesteps > 1 && (
                  <>
                    <button
                      style={{
                        ...styles.buttonIcon,
                        ...(isPlaying ? styles.buttonIconActive : {}),
                      }}
                      onClick={() => setIsPlaying(!isPlaying)}
                      title={isPlaying ? "Pause" : "Play"}
                    >
                      {isPlaying ? <Icons.Pause /> : <Icons.Play />}
                    </button>

                    <input
                      type="range"
                      min={0}
                      max={numTimesteps - 1}
                      value={currentTimestep}
                      onChange={(e) => {
                        setIsPlaying(false);
                        setCurrentTimestep(parseInt(e.target.value, 10));
                      }}
                      style={styles.slider}
                    />

                    <div style={styles.timestepDisplay}>
                      <span style={{ color: styles.colors.text }}>{currentTimestep + 1}</span>
                      <span style={{ color: styles.colors.textDimmer }}> / {numTimesteps}</span>
                    </div>

                    {currentVariable && !expanded && <div style={styles.divider} />}
                  </>
                )}

                {/* Compact colorbar in minimal mode */}
                {currentVariable && !expanded && (
                  <Colorbar
                    styles={styles}
                    preset={colorPreset}
                    min={scalarRange[0]}
                    max={scalarRange[1]}
                    variable={currentVariable}
                    compact={true}
                  />
                )}
              </div>
            </div>
          )}

          {/* Expanded controls */}
          {expanded && (
            <>
              {/* Timestep navigation */}
              {numTimesteps > 1 && (
                <div style={styles.controlSection}>
                  <div style={styles.controlRow}>
                    <button
                      style={{ ...styles.buttonIcon, ...styles.buttonIconSmall }}
                      onClick={() => setCurrentTimestep(0)}
                      title="First timestep"
                    >
                      <Icons.SkipBack />
                    </button>
                    <button
                      style={{ ...styles.buttonIcon, ...styles.buttonIconSmall }}
                      onClick={() => setCurrentTimestep(Math.max(0, currentTimestep - 1))}
                      title="Previous timestep"
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
                        <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" />
                      </svg>
                    </button>
                    <button
                      style={{ ...styles.buttonIcon, ...styles.buttonIconSmall }}
                      onClick={() => setCurrentTimestep(Math.min(numTimesteps - 1, currentTimestep + 1))}
                      title="Next timestep"
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 14, height: 14 }}>
                        <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
                      </svg>
                    </button>
                    <button
                      style={{ ...styles.buttonIcon, ...styles.buttonIconSmall }}
                      onClick={() => setCurrentTimestep(numTimesteps - 1)}
                      title="Last timestep"
                    >
                      <Icons.SkipForward />
                    </button>

                    {timeValues[currentTimestep] !== undefined && (
                      <span style={{ fontSize: "11px", color: styles.colors.textDim, marginLeft: "8px" }}>
                        Time: <span style={{ color: styles.colors.textMuted, fontFamily: "monospace" }}>
                          {formatTime(timeValues[currentTimestep])}
                        </span>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Variable, color and range controls */}
              <div style={styles.controlSection}>
                <div style={styles.controlRow}>
                  {/* Variable selector */}
                  {variableOptions.length > 0 && (
                    <div style={styles.controlGroup}>
                      <span style={styles.label}>Variable</span>
                      <select
                        value={currentVariable || ""}
                        onChange={(e) => setCurrentVariable(e.target.value || null)}
                        style={styles.select}
                      >
                        <option value="">None</option>
                        {pointVariables.length > 0 && (
                          <optgroup label="Point">
                            {pointVariables.map((v) => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </optgroup>
                        )}
                        {cellVariables.length > 0 && (
                          <optgroup label="Cell">
                            {cellVariables.map((v) => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                    </div>
                  )}

                  <div style={styles.controlGroup}>
                    <span style={styles.label}>Colors</span>
                    <select
                      value={colorPreset}
                      onChange={(e) => setColorPreset(e.target.value)}
                      style={styles.select}
                    >
                      {Object.entries(PRESET_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>{label}</option>
                      ))}
                    </select>
                  </div>

                  {currentVariable && (
                    <div style={styles.controlGroup}>
                      <span style={styles.label}>Range</span>
                      <input
                        type="number"
                        value={scalarRange[0]}
                        onChange={(e) => handleRangeChange("min", e.target.value)}
                        style={styles.input}
                        step="any"
                      />
                      <span style={{ color: styles.colors.textDimmest, fontSize: "12px" }}>to</span>
                      <input
                        type="number"
                        value={scalarRange[1]}
                        onChange={(e) => handleRangeChange("max", e.target.value)}
                        style={styles.input}
                        step="any"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Full colorbar */}
              {currentVariable && (
                <Colorbar
                  styles={styles}
                  preset={colorPreset}
                  min={scalarRange[0]}
                  max={scalarRange[1]}
                  variable={currentVariable}
                />
              )}
            </>
          )}

          {/* Expand/collapse button */}
          <button
            style={styles.expandButton}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <Icons.ChevronUp /> : <Icons.ChevronDown />}
            <span>{expanded ? "Less options" : "More options"}</span>
          </button>
        </div>
      )}
    </div>
  );
}
