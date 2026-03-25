#!/usr/bin/env bash
# =============================================================================
# stop-platform.sh — Gracefully stop all Prometheus Platform instances
#                    (equivalent to `docker compose down`)
# =============================================================================
set -euo pipefail

INSTANCES=(
  chainlit-frontend
  client-agent
  synthesis-agent
  artifact-debug-agent
  osti-research-agent
  form-filler-agent
  data-agent
  thermal-agent
  radiation-agent
  corrosion-agent
  litellm
  redis
  litellm-db
)

echo "Stopping Prometheus Platform instances..."
for inst in "${INSTANCES[@]}"; do
  if apptainer instance list | grep -q "^${inst} "; then
    echo "  stopping: $inst"
    apptainer instance stop "$inst" 2>/dev/null || true
  else
    echo "  not running: $inst (skip)"
  fi
done

echo ""
echo "All instances stopped."
apptainer instance list
