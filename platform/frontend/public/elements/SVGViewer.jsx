import { useEffect, useRef, useState } from "react";

function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof document === "undefined") return true;
    const html = document.documentElement;
    if (html.classList.contains("dark")) return true;
    if (html.getAttribute("data-theme") === "dark") return true;
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return true;
    return true;
  });

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const html = document.documentElement;
      setIsDark(
        html.classList.contains("dark") ||
        html.getAttribute("data-theme") === "dark"
      );
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return isDark;
}

export default function SVGViewer() {
  const { svgContent = "", svgUrl = "", name = "image.svg" } = props;
  const isDark = useTheme();
  const contentRef = useRef(null);
  const [displayContent, setDisplayContent] = useState(svgContent);
  const [loading, setLoading] = useState(!svgContent && !!svgUrl);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (svgContent) {
      setDisplayContent(svgContent);
      return;
    }
    if (!svgUrl) return;
    setLoading(true);
    fetch(svgUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => {
        setDisplayContent(text);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [svgContent, svgUrl]);

  const downloadSvg = () => {
    if (!displayContent) return;
    const blob = new Blob([displayContent], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name.endsWith(".svg") ? name : `${name}.svg`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const c = isDark
    ? {
        bg: "rgba(30,30,40,0.95)",
        border: "rgba(255,255,255,0.1)",
        headerBg: "rgba(255,255,255,0.02)",
        contentBg: "#1a1a24",
        text: "rgba(255,255,255,0.9)",
        textDim: "rgba(255,255,255,0.5)",
        btnBorder: "rgba(255,255,255,0.15)",
        shadow: "0 4px 24px rgba(0,0,0,0.3)",
      }
    : {
        bg: "rgba(255,255,255,0.98)",
        border: "rgba(0,0,0,0.12)",
        headerBg: "rgba(0,0,0,0.02)",
        contentBg: "#f5f5fa",
        text: "rgba(0,0,0,0.87)",
        textDim: "rgba(0,0,0,0.5)",
        btnBorder: "rgba(0,0,0,0.15)",
        shadow: "0 4px 24px rgba(0,0,0,0.08)",
      };

  const wrapStyle = {
    width: "100%",
    borderRadius: "12px",
    overflow: "hidden",
    border: `1px solid ${c.border}`,
    background: c.bg,
    boxShadow: c.shadow,
  };

  const headerStyle = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 16px",
    borderBottom: `1px solid ${c.border}`,
    background: c.headerBg,
  };

  const btnStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    padding: "4px 10px",
    borderRadius: "6px",
    border: `1px solid ${c.btnBorder}`,
    background: "transparent",
    color: c.textDim,
    fontSize: "11px",
    cursor: "pointer",
  };

  if (loading) {
    return (
      <div style={wrapStyle}>
        <div style={{ padding: "32px", textAlign: "center", color: c.textDim, fontSize: "13px" }}>
          Loading SVG…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={wrapStyle}>
        <div style={{ padding: "16px", color: "#e57373", fontSize: "13px" }}>
          Failed to load SVG: {error}
        </div>
      </div>
    );
  }

  if (!displayContent) {
    return (
      <div style={wrapStyle}>
        <div style={{ padding: "16px", color: c.textDim, fontSize: "13px" }}>
          No SVG content available.
        </div>
      </div>
    );
  }

  return (
    <div style={wrapStyle}>
      <div style={headerStyle}>
        <span style={{ fontSize: "13px", fontWeight: "500", color: c.text }}>{name}</span>
        <button style={btnStyle} onClick={downloadSvg} title="Download SVG">
          <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 13, height: 13 }}>
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zm-8 2V5h2v6h1.17L12 13.17 9.83 11H11zm-6 7h14v2H5v-2z" />
          </svg>
          Download
        </button>
      </div>
      <div
        ref={contentRef}
        style={{
          background: c.contentBg,
          padding: "16px",
          overflow: "auto",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          minHeight: "80px",
          maxHeight: "600px",
        }}
        /* SVGs come from trusted agent outputs running in the same deployment */
        /* eslint-disable-next-line react/no-danger */
        dangerouslySetInnerHTML={{ __html: displayContent }}
      />
    </div>
  );
}
