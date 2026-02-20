import { useEffect, useMemo, useRef, useState } from "react";

const MERMAID_SRC = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";

let mermaidPromise = null;

function loadMermaid() {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Mermaid requires a browser environment."));
  }

  if (window.mermaid) {
    return Promise.resolve(window.mermaid);
  }

  if (mermaidPromise) {
    return mermaidPromise;
  }

  mermaidPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = MERMAID_SRC;
    script.async = true;

    script.onload = () => {
      if (window.mermaid) {
        resolve(window.mermaid);
      } else {
        reject(new Error("Mermaid loaded but window.mermaid was not set."));
      }
    };

    script.onerror = () => reject(new Error("Failed to load Mermaid script."));

    document.head.appendChild(script);
  });

  return mermaidPromise;
}

function detectTheme() {
  if (typeof document !== "undefined") {
    const html = document.documentElement;
    const body = document.body;
    if (html.classList.contains("dark") || body.classList.contains("dark")) {
      return "dark";
    }
    if (html.getAttribute("data-theme") === "dark") {
      return "dark";
    }
  }
  if (typeof window !== "undefined" && window.matchMedia) {
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
  }
  return "default";
}

function normalizeConfig(config) {
  if (!config) {
    return {};
  }
  if (typeof config === "string") {
    try {
      return JSON.parse(config);
    } catch (err) {
      return {};
    }
  }
  if (typeof config === "object") {
    return config;
  }
  return {};
}

export default function MermaidViewer() {
  const {
    diagram,
    title,
    config,
    theme,
    height = "auto",
    width = "100%",
  } = props || {};
  const containerRef = useRef(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [view, setView] = useState("diagram");
  const [copied, setCopied] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  const configKey = useMemo(
    () => JSON.stringify(normalizeConfig(config) || {}),
    [config]
  );

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      if (!diagram || !containerRef.current) {
        setStatus("error");
        setError("No Mermaid diagram provided.");
        return;
      }

      setStatus("loading");
      setError("");
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }

      try {
        const mermaid = await loadMermaid();
        if (cancelled) return;

        const resolvedConfig = normalizeConfig(config);
        const resolvedTheme = theme || detectTheme();
        mermaid.initialize({
          startOnLoad: false,
          theme: resolvedTheme,
          ...resolvedConfig,
        });

        const id = `mermaid-${Math.random().toString(36).slice(2)}`;
        const renderFn = mermaid.render;

        const result = renderFn(id, diagram);
        if (result && typeof result.then === "function") {
          const { svg, bindFunctions } = await result;
          if (cancelled || !containerRef.current) return;
          containerRef.current.innerHTML = svg;
          if (bindFunctions) {
            bindFunctions(containerRef.current);
          }
          setStatus("ready");
          return;
        }

        if (result && result.svg) {
          if (cancelled || !containerRef.current) return;
          containerRef.current.innerHTML = result.svg;
          if (result.bindFunctions) {
            result.bindFunctions(containerRef.current);
          }
          setStatus("ready");
          return;
        }

        renderFn(
          id,
          diagram,
          (svg, bindFunctions) => {
            if (cancelled || !containerRef.current) return;
            containerRef.current.innerHTML = svg;
            if (bindFunctions) {
              bindFunctions(containerRef.current);
            }
            setStatus("ready");
          },
          containerRef.current
        );
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setError(err?.message || String(err));
        setView("code");
      }
    }

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [diagram, configKey, theme]);

  const wrapperStyle = {
    width,
    height: height === "auto" ? "auto" : height,
    overflowX: "auto",
    overflowY: "hidden",
    padding: "8px 0",
  };

  const tabStyle = (active) => ({
    fontSize: 11,
    padding: "4px 8px",
    borderRadius: 6,
    border: "1px solid rgba(120, 120, 120, 0.35)",
    background: active ? "rgba(120, 120, 120, 0.15)" : "transparent",
    color: "inherit",
    cursor: "pointer",
  });

  const downloadSvg = () => {
    if (!containerRef.current) return;
    const svg = containerRef.current.querySelector("svg");
    if (!svg) {
      setDownloadError("Diagram is not ready yet.");
      return;
    }

    setDownloadError("");

    const serializer = new XMLSerializer();
    let svgText = serializer.serializeToString(svg);
    if (!svgText.includes("http://www.w3.org/2000/svg")) {
      svgText = svgText.replace(
        "<svg",
        '<svg xmlns="http://www.w3.org/2000/svg"'
      );
    }

    const svgBlob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "mermaid-diagram.svg";
    link.click();
    URL.revokeObjectURL(url);
  };

  const downloadPng = async () => {
    if (!containerRef.current) return;
    const svg = containerRef.current.querySelector("svg");
    if (!svg) {
      setDownloadError("Diagram is not ready yet.");
      return;
    }

    setDownloadError("");

    try {
      const serializer = new XMLSerializer();
      let svgText = serializer.serializeToString(svg);
      svgText = svgText.replace(/@import[^;]+;/g, "");

      if (!svgText.includes("http://www.w3.org/2000/svg")) {
        svgText = svgText.replace(
          "<svg",
          '<svg xmlns="http://www.w3.org/2000/svg"'
        );
      }

      const svgBlob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(svgBlob);

      const image = new Image();
      image.crossOrigin = "anonymous";
      image.onload = () => {
        const width =
          image.naturalWidth ||
          svg.viewBox.baseVal.width ||
          svg.getBoundingClientRect().width ||
          800;
        const height =
          image.naturalHeight ||
          svg.viewBox.baseVal.height ||
          svg.getBoundingClientRect().height ||
          600;

        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.ceil(width));
        canvas.height = Math.max(1, Math.ceil(height));

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

        URL.revokeObjectURL(url);

        try {
          const pngUrl = canvas.toDataURL("image/png");
          const link = document.createElement("a");
          link.href = pngUrl;
          link.download = "mermaid-diagram.png";
          link.click();
        } catch (err) {
          setDownloadError(
            "PNG export blocked by the browser. Try the SVG download instead."
          );
        }
      };

      image.onerror = () => {
        URL.revokeObjectURL(url);
        setDownloadError("Unable to export image.");
      };

      image.src = url;
    } catch (err) {
      setDownloadError("Unable to export image.");
    }
  };

  const copyCode = async () => {
    if (!diagram) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(diagram);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = diagram;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (err) {
      setCopied(false);
    }
  };

  return (
    <div style={wrapperStyle}>
      {title ? (
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            marginBottom: 8,
            opacity: 0.8,
          }}
        >
          {title}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 6, marginBottom: 8, alignItems: "center" }}>
        <button
          type="button"
          style={tabStyle(view === "diagram")}
          onClick={() => setView("diagram")}
        >
          Diagram
        </button>
        <button
          type="button"
          style={tabStyle(view === "code")}
          onClick={() => setView("code")}
        >
          Code
        </button>
        {view === "diagram" ? (
          <button
            type="button"
            onClick={downloadPng}
            style={{
              marginLeft: "auto",
              fontSize: 11,
              padding: "4px 8px",
              borderRadius: 6,
              border: "1px solid rgba(120, 120, 120, 0.35)",
              background: "rgba(120, 120, 120, 0.12)",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            Download PNG
          </button>
        ) : null}
        {view === "diagram" ? (
          <button
            type="button"
            onClick={downloadSvg}
            style={{
              fontSize: 11,
              padding: "4px 8px",
              borderRadius: 6,
              border: "1px solid rgba(120, 120, 120, 0.35)",
              background: "rgba(120, 120, 120, 0.12)",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            Download SVG
          </button>
        ) : null}
      </div>
      <div style={{ display: view === "diagram" ? "block" : "none" }}>
        {status === "loading" ? (
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            Rendering diagram...
          </div>
        ) : null}
        {status === "error" ? (
          <div style={{ fontSize: 12, color: "#e57373" }}>
            Mermaid render failed: {error}
          </div>
        ) : null}
        {downloadError ? (
          <div style={{ fontSize: 12, color: "#e57373", marginBottom: 6 }}>
            {downloadError}
          </div>
        ) : null}
        <div
          style={{
            borderRadius: 10,
            border: "1px solid rgba(120, 120, 120, 0.2)",
            background: "rgba(120, 120, 120, 0.05)",
            padding: "12px",
            overflow: "auto",
          }}
        >
          <div ref={containerRef} />
        </div>
      </div>
      <div
        style={{
          display: view === "code" ? "block" : "none",
          position: "relative",
        }}
      >
        <button
          type="button"
          onClick={copyCode}
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            zIndex: 1,
            fontSize: 11,
            padding: "4px 8px",
            borderRadius: 6,
            border: "1px solid rgba(120, 120, 120, 0.35)",
            background: "rgba(120, 120, 120, 0.12)",
            color: "inherit",
            cursor: "pointer",
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <pre
          style={{
            margin: 0,
            padding: "28px 12px 10px",
            fontSize: 12,
            borderRadius: 8,
            background: "rgba(120, 120, 120, 0.08)",
            border: "1px solid rgba(120, 120, 120, 0.2)",
            overflowX: "auto",
            whiteSpace: "pre",
          }}
        >
          {diagram || ""}
        </pre>
      </div>
    </div>
  );
}
