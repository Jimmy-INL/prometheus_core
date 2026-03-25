#!/usr/bin/env bash
SIF_DIR="${SIF_DIR:-sif}"
DEF_DIR="${DEF_DIR:-defs}"
ENV_FILE="${ENV_FILE:-env/prometheus.env}"

set -euo pipefail

while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --sif-dir) SIF_DIR="$2"; shift 2 ;;
    --def-dir) DEF_DIR="$2"; shift 2 ;;
    --env)     ENV_FILE="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE"; exit 1
fi

source "$ENV_FILE"

FILTER=("$@")
mkdir -p "$SIF_DIR"

build_image() {
  local name="$1"
  local def="$2"
  shift 2
  local extra_args=("$@")

  if [[ ${#FILTER[@]} -gt 0 ]]; then
    local match=0
    for f in "${FILTER[@]}"; do [[ "$f" == "$name" ]] && match=1; done
    [[ $match -eq 0 ]] && return
  fi

  local sif="${SIF_DIR}/${name}.sif"
  echo ""
  echo "──────────────────────────────────────────"
  echo "  Building: ${DEF_DIR}/$name.def  →  $sif"
  echo "──────────────────────────────────────────"
  apptainer build --force "${extra_args[@]}" "$sif" "${DEF_DIR}/${def}"
}

# Infrastructure
#build_image litellm-db        litellm-db.def
#build_image litellm           litellm.def
#build_image redis             redis.def
#build_image client-agent      client-agent.def
#build_image chainlit-frontend chainlit-frontend.def
exit 0

# Specialist agents — ports sourced from env file
declare -A SPECIALIST_PORTS=(
  [artifact-debug-agent]="$PORT_ARTIFACT_DEBUG_AGENT"
  [corrosion-agent]="$PORT_CORROSION_AGENT"
  [data-agent]="$PORT_DATA_AGENT"
  [form-filler-agent]="$PORT_FORM_FILLER_AGENT"
  [radiation-agent]="$PORT_RADIATION_AGENT"
  [synthesis-agent]="$PORT_SYNTHESIS_AGENT"
  [thermal-agent]="$PORT_THERMAL_AGENT"
)

for agent_name in "${!SPECIALIST_PORTS[@]}"; do
  port="${SPECIALIST_PORTS[$agent_name]}"
  build_image "$agent_name" agent-template.def \
    --build-arg "AGENT_NAME=${agent_name}" \
    --build-arg "AGENT_PORT=${port}"
done

# OSTI has its own def
build_image osti-research-agent osti-research-agent.def \
  --build-arg "AGENT_PORT=${PORT_OSTI_RESEARCH_AGENT}"

echo ""
echo "=== Build complete ==="
ls -lh "${SIF_DIR}/"
