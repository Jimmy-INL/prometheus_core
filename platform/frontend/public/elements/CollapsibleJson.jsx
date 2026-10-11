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

import React, { useState } from 'react';

const COLLAPSED_ROWS = 10;
const LINE_HEIGHT_PX = 20; // approximate px per line in the monospace block

export default function CollapsibleJson(props) {
  const data = props?.data;
  const name = props?.name || 'JSON';
  const description = props?.description || '';
  const jsonType = props?.json_type || '';

  const formatted = React.useMemo(() => {
    if (data == null) return '(no data)';
    try {
      const parsed = typeof data === 'string' ? JSON.parse(data) : data;
      return JSON.stringify(parsed, null, 2);
    } catch {
      return String(data);
    }
  }, [data]);

  const lines = formatted.split('\n');
  const isExpandable = lines.length > COLLAPSED_ROWS;

  const [expanded, setExpanded] = useState(false);

  const collapsedHeight = COLLAPSED_ROWS * LINE_HEIGHT_PX;
  const displayedText = !isExpandable || expanded ? formatted : lines.slice(0, COLLAPSED_ROWS).join('\n');

  return (
    <div style={{
      fontFamily: 'sans-serif',
      fontSize: '0.875rem',
      border: '1px solid #e2e8f0',
      borderRadius: '6px',
      overflow: 'hidden',
      marginTop: '0.5rem',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.4rem 0.75rem',
        background: '#f8fafc',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <span style={{ fontWeight: 600, color: '#1e293b' }}>
          {name}
          {jsonType && (
            <span style={{
              marginLeft: '0.5rem',
              fontSize: '0.75rem',
              fontWeight: 400,
              color: '#64748b',
              background: '#e2e8f0',
              borderRadius: '4px',
              padding: '1px 6px',
            }}>
              {jsonType}
            </span>
          )}
        </span>
        {isExpandable && (
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              fontSize: '0.75rem',
              color: '#3b82f6',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '2px 6px',
              borderRadius: '4px',
            }}
          >
            {expanded ? '▲ Collapse' : '▼ Expand'}
          </button>
        )}
      </div>

      {/* Description */}
      {description && (
        <div style={{
          padding: '0.3rem 0.75rem',
          fontSize: '0.8rem',
          color: '#64748b',
          borderBottom: '1px solid #f1f5f9',
          background: '#fafafa',
        }}>
          {description}
        </div>
      )}

      {/* Code block */}
      <div style={{ position: 'relative' }}>
        <pre style={{
          margin: 0,
          padding: '0.75rem',
          fontSize: '0.78rem',
          lineHeight: `${LINE_HEIGHT_PX}px`,
          overflowX: 'auto',
          overflowY: 'hidden',
          background: '#1e1e2e',
          color: '#cdd6f4',
          maxHeight: !isExpandable || expanded ? 'none' : `${collapsedHeight}px`,
          whiteSpace: 'pre',
        }}>
          {displayedText}
        </pre>

        {/* Fade overlay when collapsed */}
        {isExpandable && !expanded && (
          <div
            onClick={() => setExpanded(true)}
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: '3rem',
              background: 'linear-gradient(transparent, #1e1e2e)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'center',
              paddingBottom: '4px',
            }}
          >
            <span style={{
              color: '#94a3b8',
              fontSize: '0.75rem',
              userSelect: 'none',
            }}>
              {lines.length - COLLAPSED_ROWS} more lines — click to expand
            </span>
          </div>
        )}
      </div>

      {/* Bottom collapse button when expanded */}
      {isExpandable && expanded && (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          padding: '0.35rem',
          background: '#f8fafc',
          borderTop: '1px solid #e2e8f0',
        }}>
          <button
            onClick={() => setExpanded(false)}
            style={{
              fontSize: '0.75rem',
              color: '#3b82f6',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '2px 6px',
            }}
          >
            ▲ Collapse
          </button>
        </div>
      )}
    </div>
  );
}
