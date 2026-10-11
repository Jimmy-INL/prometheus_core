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

import assert from "node:assert/strict";
import test from "node:test";

import { normalizeMime } from "./mime.ts";

test("strips parameters, whitespace and case", () => {
  assert.equal(normalizeMime("Text/CSV; charset=UTF-8"), "text/csv");
  assert.equal(normalizeMime("  application/json  "), "application/json");
});

test("missing input is an empty string", () => {
  assert.equal(normalizeMime(undefined), "");
  assert.equal(normalizeMime(null), "");
  assert.equal(normalizeMime(""), "");
});
