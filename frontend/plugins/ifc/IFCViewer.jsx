import { useEffect, useRef, useState, useCallback, useMemo } from "react";

// SVG Icons as components
const Icons = {
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
  ZoomIn: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zm.5-7H9v2H7v1h2v2h1v-2h2V9h-2z" />
    </svg>
  ),
  ZoomOut: () => (
    <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 16, height: 16 }}>
      <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zM7 9h5v1H7z" />
    </svg>
  ),
};

/**
 * Hook to detect current theme (dark or light mode)
 */
function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof document !== "undefined") {
      const html = document.documentElement;
      const body = document.body;
      if (html.classList.contains("dark")) return true;
      if (body.classList.contains("dark")) return true;
      if (html.getAttribute("data-theme") === "dark") return true;
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return true;
      }
    }
    return true;
  });

  useEffect(() => {
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

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e) => {
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
        bg: "linear-gradient(180deg, rgba(30,30,40,0.95) 0%, rgba(20,20,30,0.98) 100%)",
        bgSolid: "#1e1e28",
        border: "rgba(255,255,255,0.1)",
        borderLight: "rgba(255,255,255,0.08)",
        text: "rgba(255,255,255,0.9)",
        textMuted: "rgba(255,255,255,0.7)",
        textDim: "rgba(255,255,255,0.5)",
        canvas: "#14141e",
        headerBg: "rgba(255,255,255,0.02)",
        controlBorder: "rgba(255,255,255,0.12)",
        controlBgHover: "rgba(255,255,255,0.06)",
        badgeBg: "rgba(99,102,241,0.2)",
        badgeText: "rgb(165,180,252)",
        shadow: "0 4px 24px rgba(0,0,0,0.3)",
        sceneBg: 0x14141e,
      }
    : {
        bg: "linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,249,250,0.98) 100%)",
        bgSolid: "#ffffff",
        border: "rgba(0,0,0,0.12)",
        borderLight: "rgba(0,0,0,0.08)",
        text: "rgba(0,0,0,0.87)",
        textMuted: "rgba(0,0,0,0.7)",
        textDim: "rgba(0,0,0,0.5)",
        canvas: "#e8e8f0",
        headerBg: "rgba(0,0,0,0.02)",
        controlBorder: "rgba(0,0,0,0.12)",
        controlBgHover: "rgba(0,0,0,0.08)",
        badgeBg: "rgba(99,102,241,0.12)",
        badgeText: "rgb(79,70,229)",
        shadow: "0 4px 24px rgba(0,0,0,0.08)",
        sceneBg: 0xe8e8f0,
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
    loadingOverlay: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: isDark ? "rgba(20,20,30,0.9)" : "rgba(255,255,255,0.9)",
      color: colors.textDim,
      fontSize: "14px",
    },
    infoOverlay: {
      position: "absolute",
      bottom: "12px",
      left: "12px",
      background: isDark ? "rgba(0,0,0,0.8)" : "rgba(255,255,255,0.95)",
      backdropFilter: "blur(8px)",
      padding: "8px 12px",
      borderRadius: "8px",
      fontSize: "11px",
      color: colors.text,
      border: `1px solid ${colors.border}`,
    },
  };
}

/**
 * IFCViewer - ThatOpen engine_components based viewer for IFC files.
 */
export default function IFCViewer() {
  const containerRef = useRef(null);
  const viewerContainerRef = useRef(null);
  const ifcState = useRef(null);

  const isDark = useTheme();
  const styles = useMemo(() => getStyles(isDark), [isDark]);

  const [isLoading, setIsLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState("Initializing...");
  const [error, setError] = useState(null);
  const [ifcReady, setIfcReady] = useState(!!window.OBC);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);

  const {
    datasetId,
    fileUrl,
    filename = "model.ifc",
    height = "500px",
  } = props;

  // Wait for ifc-bundle.js
  useEffect(() => {
    if (window.OBC) {
      setIfcReady(true);
      return;
    }
    const handleIfcReady = () => setIfcReady(true);
    window.addEventListener("ifc-ready", handleIfcReady);
    return () => window.removeEventListener("ifc-ready", handleIfcReady);
  }, []);

  // Update scene background when theme changes
  useEffect(() => {
    if (ifcState.current?.scene) {
      const THREE = window.THREE;
      if (THREE) {
        ifcState.current.scene.three.background = new THREE.Color(styles.colors.sceneBg);
      }
    }
  }, [isDark, styles.colors.sceneBg]);

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
      // Trigger resize after fullscreen change
      setTimeout(() => {
        if (ifcState.current?.components) {
          window.dispatchEvent(new Event('resize'));
        }
      }, 100);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  // Initialize ThatOpen viewer and load IFC
  useEffect(() => {
    if (!ifcReady || !containerRef.current) return;

    const OBC = window.OBC;
    const THREE = window.THREE;

    if (!OBC || !THREE) {
      setError("ThatOpen components not loaded");
      setIsLoading(false);
      return;
    }

    let disposed = false;

    async function initViewer() {
      try {
        setLoadingMessage("Creating viewer...");

        // Clear container
        containerRef.current.innerHTML = "";

        // Create components instance
        const components = new OBC.Components();

        // Create and setup world
        const worlds = components.get(OBC.Worlds);
        const world = worlds.create();

        // Setup scene
        world.scene = new OBC.SimpleScene(components);
        world.scene.setup();
        world.scene.three.background = new THREE.Color(styles.colors.sceneBg);

        // Setup renderer
        world.renderer = new OBC.SimpleRenderer(components, containerRef.current);

        // Setup camera
        world.camera = new OBC.SimpleCamera(components);

        // Initialize components
        components.init();

        // Enable camera controls
        world.camera.controls.setLookAt(10, 10, 10, 0, 0, 0);

        // Add ambient light
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        world.scene.three.add(ambientLight);

        // Add directional light
        const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
        directionalLight.position.set(5, 10, 3);
        world.scene.three.add(directionalLight);

        // Store state
        ifcState.current = {
          components,
          world,
          scene: world.scene,
          renderer: world.renderer,
          camera: world.camera,
        };

        if (disposed) {
          components.dispose();
          return;
        }

        // Setup IFC loader
        setLoadingMessage("Setting up IFC loader...");

        const fragmentsManager = components.get(OBC.FragmentsManager);
        const ifcLoader = components.get(OBC.IfcLoader);

        // Configure WASM path from CDN
        await ifcLoader.setup({
          wasm: {
            path: "https://unpkg.com/web-ifc@0.0.68/",
            absolute: true,
          },
        });

        ifcState.current.ifcLoader = ifcLoader;
        ifcState.current.fragmentsManager = fragmentsManager;

        if (disposed) {
          components.dispose();
          return;
        }

        // Load the IFC file
        setLoadingMessage("Loading IFC model...");

        const response = await fetch(fileUrl);
        if (!response.ok) {
          throw new Error(`Failed to fetch IFC file: HTTP ${response.status}`);
        }

        const buffer = await response.arrayBuffer();
        const uint8Array = new Uint8Array(buffer);

        if (disposed) {
          components.dispose();
          return;
        }

        setLoadingMessage("Processing IFC data...");
        const model = await ifcLoader.load(uint8Array);

        if (disposed) {
          components.dispose();
          return;
        }

        // Add model to scene
        world.scene.three.add(model);

        // Fit camera to model
        setLoadingMessage("Fitting view...");

        // Calculate bounding box
        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim * 2;

        world.camera.controls.setLookAt(
          center.x + distance,
          center.y + distance * 0.5,
          center.z + distance,
          center.x,
          center.y,
          center.z
        );

        // Store model info
        setModelInfo({
          elements: model.children?.length || 0,
          size: `${(buffer.byteLength / 1024 / 1024).toFixed(2)} MB`,
        });

        ifcState.current.model = model;
        ifcState.current.boundingBox = box;
        ifcState.current.center = center;

        setIsLoading(false);
      } catch (err) {
        console.error("Failed to initialize IFC viewer:", err);
        if (!disposed) {
          setError(`Failed to load IFC: ${err.message}`);
          setIsLoading(false);
        }
      }
    }

    initViewer();

    return () => {
      disposed = true;
      if (ifcState.current?.components) {
        try {
          ifcState.current.components.dispose();
        } catch (e) {
          console.warn("Error disposing components:", e);
        }
      }
      ifcState.current = null;
    };
  }, [ifcReady, fileUrl, styles.colors.sceneBg]);

  const handleResetCamera = useCallback(() => {
    if (!ifcState.current?.camera || !ifcState.current?.center || !ifcState.current?.boundingBox) return;

    const THREE = window.THREE;
    if (!THREE) return;

    const box = ifcState.current.boundingBox;
    const center = ifcState.current.center;
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const distance = maxDim * 2;

    ifcState.current.camera.controls.setLookAt(
      center.x + distance,
      center.y + distance * 0.5,
      center.z + distance,
      center.x,
      center.y,
      center.z
    );
  }, []);

  if (!ifcReady) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>Loading ThatOpen components...</div>
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

  return (
    <div
      ref={viewerContainerRef}
      style={isFullscreen ? { ...styles.container, ...styles.containerFullscreen } : styles.container}
    >
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.title}>
          <span>IFC Viewer</span>
          <span style={styles.badge}>{filename}</span>
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
      <div
        style={{
          ...styles.canvasWrapper,
          height: isFullscreen ? undefined : height,
          flex: isFullscreen ? 1 : undefined,
        }}
      >
        <div
          ref={containerRef}
          style={{ width: "100%", height: isFullscreen ? "100%" : height }}
        />

        {/* Loading overlay */}
        {isLoading && (
          <div style={styles.loadingOverlay}>
            {loadingMessage}
          </div>
        )}

        {/* Model info overlay */}
        {!isLoading && modelInfo && (
          <div style={styles.infoOverlay}>
            <span style={{ marginRight: "12px" }}>
              <span style={{ color: styles.colors.textDim }}>Size: </span>
              <span>{modelInfo.size}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
