#!/usr/bin/env bash
# =============================================================================
# status.sh — Show running instances and do a quick TCP health check
#             (equivalent to `docker compose ps`)
# =============================================================================
set -euo pipefail

ENV_FILE="${ENV_FILE:-env/prometheus.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE"; exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

declare -A PORT_MAP=(
  [litellm-db]="$PORT_LITELLM_DB"
  [agent-redis]="$PORT_REDIS"
  [litellm-proxy]="$PORT_LITELLM"
  [corrosion-agent]="$PORT_CORROSION_AGENT"
  [radiation-agent]="$PORT_RADIATION_AGENT"
  [thermal-agent]="$PORT_THERMAL_AGENT"
  [data-agent]="$PORT_DATA_AGENT"
  [form-filler-agent]="$PORT_FORM_FILLER_AGENT"
  [osti-research-agent]="$PORT_OSTI_RESEARCH_AGENT"
  [artifact-debug-agent]="$PORT_ARTIFACT_DEBUG_AGENT"
  [synthesis-agent]="$PORT_SYNTHESIS_AGENT"
  [client-agent]="$PORT_CLIENT_AGENT"
  [chainlit-frontend]="$PORT_CHAINLIT"
)

echo ""
echo "=== Apptainer Instances ==="
apptainer instance list
echo ""

echo "=== TCP Port Health ==="
printf "%-30s %-8s %-8s\n" "SERVICE" "PORT" "STATUS"
printf "%-30s %-8s %-8s\n" "-------" "----" "------"

for svc in "${!PORT_MAP[@]}"; do
  port="${PORT_MAP[$svc]}"
  if nc -z localhost "$port" 2>/dev/null; then
    status="UP"
  else
    status="DOWN"
  fi
  printf "%-30s %-8s %-8s\n" "$svc" "$port" "$status"
done | sort
echo ""
