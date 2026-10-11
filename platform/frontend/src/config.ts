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

// Mirrors the relevant UI config from frontend/config.yml.
// Keep these two files in sync when updating welcome text or suggestions.
export const chatIntro = "Welcome to the Prometheus Platform.";
export const chatSuggestionTitle = "What would you like to do today?";

//  "Design a Rankine cycle based power generation system for a Sodium Fast Reactor. Core power rating is 390 MW, turbine output is 170.9 MW",
export const workflowSuggestions = [
  "Create a single-loop PWR primary coolant system with an RPV, SG, and a Pump connected in a closed loop",
  "Create a CAD file of a butterfly valve with 6 holes with a diameter of 5cm each for a pipe diameter of 0.9m",
  "Run FTL Safety Analysis",
  "Perform a literature search on suitable wall materials for molten salt reactors",
  "Perform a thermal analysis of SS316 at 400C",
  "Do a comprehensive material analysis of SS347",
  "Make an image with the word Success in red in it",
];
