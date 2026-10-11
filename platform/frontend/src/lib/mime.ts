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

/**
 * Pure MIME helpers shared by modules that must stay free of React and highlight.js
 * (so `node --test` can load them): `elements.ts`, `highlight/language.ts`, `table/csv.ts`.
 */

/** A MIME type without its parameters (`; charset=...`), trimmed and lowercased. */
export function normalizeMime(mime: string | null | undefined): string {
  return (mime ?? "").split(";", 1)[0].trim().toLowerCase();
}
