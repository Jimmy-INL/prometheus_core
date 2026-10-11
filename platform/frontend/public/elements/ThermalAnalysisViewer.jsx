// This file is part of Prometheus
// https://inl.gov/super-intelligence/prometheus/
//
// Copyright 2026 Battelle Energy Alliance, LLC
// All rights reserved, see NOTICE.txt for full restrictions
// https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
//
// Licensed under the MIT License, please see LICENSE for details
// https://github.com/idaholab/prometheus_core/blob/main/LICENSE
//
// SPDX-License-Identifier: MIT

import { useEffect, useState } from "react";

function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof document === "undefined") return true;
    const html = document.documentElement;
    if (html.classList.contains("dark")) return true;
    if (html.getAttribute("data-theme") === "dark") return true;
    return !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
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

function formatLabel(key) {
  return String(key || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (typeof value === "number") {
    if (value !== 0 && Math.abs(value) < 0.001) return value.toExponential(2);
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function ValueTree({ value }) {
  if (Array.isArray(value)) {
    return (
      <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
        {value.map((item, index) => (
          <li key={index} style={{ marginBottom: "6px" }}>
            {typeof item === "object" && item !== null ? <ValueTree value={item} /> : formatValue(item)}
          </li>
        ))}
      </ul>
    );
  }

  if (value && typeof value === "object") {
    return (
      <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
        {Object.entries(value).map(([key, nestedValue]) => (
          <li key={key} style={{ marginBottom: "6px" }}>
            <strong>{formatLabel(key)}:</strong>{" "}
            {typeof nestedValue === "object" && nestedValue !== null ? (
              <ValueTree value={nestedValue} />
            ) : (
              formatValue(nestedValue)
            )}
          </li>
        ))}
      </ul>
    );
  }

  return <span>{formatValue(value)}</span>;
}

export default function ThermalAnalysisViewer() {
  const { name = "thermal_analysis", description = "", analysis = {} } = props;
  const isDark = useTheme();

  const colors = isDark
    ? {
        bg: "linear-gradient(180deg, rgba(24,30,36,0.98), rgba(16,20,26,0.98))",
        border: "rgba(255,255,255,0.12)",
        header: "#f3f5f7",
        text: "rgba(255,255,255,0.88)",
        dim: "rgba(255,255,255,0.6)",
        panel: "rgba(255,255,255,0.04)",
        accent: "#ffb86b",
        ok: "#8fd694",
        warn: "#ffd166",
        bad: "#ff7b72",
      }
    : {
        bg: "linear-gradient(180deg, rgba(255,250,244,0.98), rgba(248,244,239,0.98))",
        border: "rgba(73,57,42,0.15)",
        header: "#2b241c",
        text: "#46392d",
        dim: "rgba(70,57,45,0.68)",
        panel: "rgba(132,98,64,0.06)",
        accent: "#b96a24",
        ok: "#2f7d4c",
        warn: "#9b6a00",
        bad: "#b23a32",
      };

  const status = String(analysis.status || "unknown").toLowerCase();
  const statusColor =
    status === "acceptable" ? colors.ok : status === "critical" ? colors.bad : colors.warn;

  const headlineItems = [
    ["Material", analysis.material_id],
    ["Status", analysis.status],
    ["Operating Temperature", analysis.operating_temperature_c],
    ["Thermal Stress (MPa)", analysis.thermal_stress_mpa],
    ["Fatigue Usage Factor", analysis.thermal_fatigue_usage_factor],
    ["Confidence", analysis.confidence],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");

  const sections = [
    ["Cycle Categories", analysis.cycle_categories],
    ["Fatigue Analysis", analysis.fatigue_analysis],
    ["Creep Analysis", analysis.creep_analysis],
    ["Recommendations", analysis.recommendations],
  ].filter(([, value]) => value && (Array.isArray(value) ? value.length > 0 : Object.keys(value).length > 0));

  return (
    <div
      style={{
        width: "100%",
        borderRadius: "16px",
        border: `1px solid ${colors.border}`,
        background: colors.bg,
        color: colors.text,
        padding: "18px 20px",
        boxShadow: isDark ? "0 12px 36px rgba(0,0,0,0.28)" : "0 12px 32px rgba(108,84,59,0.12)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
        <div>
          <div style={{ fontSize: "12px", letterSpacing: "0.08em", textTransform: "uppercase", color: colors.accent }}>
            Thermal Analysis
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: colors.header }}>
            {analysis.material_id || name}
          </div>
          {description ? (
            <div style={{ marginTop: "4px", fontSize: "13px", color: colors.dim }}>{description}</div>
          ) : null}
        </div>
        <div
          style={{
            borderRadius: "999px",
            padding: "6px 12px",
            fontSize: "12px",
            fontWeight: 700,
            textTransform: "uppercase",
            color: statusColor,
            border: `1px solid ${statusColor}44`,
            background: `${statusColor}12`,
          }}
        >
          {analysis.status || "unknown"}
        </div>
      </div>

      <div
        style={{
          marginTop: "16px",
          padding: "14px 16px",
          borderRadius: "12px",
          background: colors.panel,
        }}
      >
        <ul style={{ margin: 0, paddingLeft: "18px" }}>
          {headlineItems.map(([label, value]) => (
            <li key={label} style={{ marginBottom: "6px" }}>
              <strong>{label}:</strong> {formatValue(value)}
            </li>
          ))}
        </ul>
      </div>

      {sections.map(([title, value]) => (
        <div key={title} style={{ marginTop: "16px" }}>
          <div style={{ fontSize: "13px", fontWeight: 700, color: colors.header }}>{title}</div>
          <div
            style={{
              marginTop: "8px",
              padding: "12px 14px",
              borderRadius: "12px",
              background: colors.panel,
            }}
          >
            <ValueTree value={value} />
          </div>
        </div>
      ))}
    </div>
  );
}
