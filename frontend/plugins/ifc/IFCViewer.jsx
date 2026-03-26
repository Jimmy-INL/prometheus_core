import { useEffect, useMemo, useState } from "react";

function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof document === "undefined") return true;
    const html = document.documentElement;
    const body = document.body;
    if (html.classList.contains("dark")) return true;
    if (body.classList.contains("dark")) return true;
    if (html.getAttribute("data-theme") === "dark") return true;
    return !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const html = document.documentElement;
      const body = document.body;
      setIsDark(
        html.classList.contains("dark") ||
          body.classList.contains("dark") ||
          html.getAttribute("data-theme") === "dark"
      );
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return isDark;
}

function getStyles(isDark) {
  const colors = isDark
    ? {
        bg: "linear-gradient(180deg, rgba(30,30,40,0.95) 0%, rgba(20,20,30,0.98) 100%)",
        headerBg: "rgba(255,255,255,0.03)",
        border: "rgba(255,255,255,0.1)",
        text: "rgba(255,255,255,0.88)",
        muted: "rgba(255,255,255,0.6)",
        badgeBg: "rgba(99,102,241,0.2)",
        badgeText: "rgb(165,180,252)",
      }
    : {
        bg: "linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,249,250,0.98) 100%)",
        headerBg: "rgba(0,0,0,0.02)",
        border: "rgba(0,0,0,0.1)",
        text: "rgba(0,0,0,0.84)",
        muted: "rgba(0,0,0,0.58)",
        badgeBg: "rgba(99,102,241,0.12)",
        badgeText: "rgb(79,70,229)",
      };

  return {
    colors,
    container: {
      width: "100%",
      overflow: "hidden",
      borderRadius: "12px",
      border: `1px solid ${colors.border}`,
      background: colors.bg,
    },
    header: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "12px",
      padding: "10px 16px",
      background: colors.headerBg,
      borderBottom: `1px solid ${colors.border}`,
    },
    title: {
      fontSize: "13px",
      fontWeight: 600,
      color: colors.text,
    },
    subtitle: {
      fontSize: "12px",
      color: colors.muted,
    },
    badge: {
      borderRadius: "999px",
      padding: "4px 10px",
      fontSize: "11px",
      fontWeight: 600,
      background: colors.badgeBg,
      color: colors.badgeText,
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
      maxWidth: "60%",
    },
    frame: {
      width: "100%",
      border: 0,
      display: "block",
      background: isDark ? "#111319" : "#f3f4f8",
    },
    error: {
      padding: "16px",
      color: "#b91c1c",
      fontSize: "13px",
    },
  };
}

export default function IFCViewer() {
  const isDark = useTheme();
  const styles = useMemo(() => getStyles(isDark), [isDark]);

  const {
    fileUrl,
    filename = "model.ifc",
    height = "500px",
  } = props;

  if (!fileUrl) {
    return <div style={styles.error}>No IFC file URL was provided to the viewer.</div>;
  }

  const search = new URLSearchParams({
    fileUrl,
    filename,
    theme: isDark ? "dark" : "light",
  });

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <div style={styles.title}>IFC Viewer</div>
          <div style={styles.subtitle}>ThatOpen standalone viewer</div>
        </div>
        <div style={styles.badge}>{filename}</div>
      </div>
      <iframe
        title={`IFC Viewer - ${filename}`}
        src={`/public/ifc-viewer.html?${search.toString()}`}
        style={{ ...styles.frame, height }}
        loading="lazy"
        allowFullScreen
      />
    </div>
  );
}
