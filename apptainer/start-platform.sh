#!/usr/bin/env bash
# =============================================================================
# start-platform.sh — Prometheus Platform launcher (Apptainer equivalent of
#                      `docker compose up -d`)
#
# Usage:
#   ./start-platform.sh [--env env/prometheus.env] [--sif-dir sif/]
#
# Prerequisites:
#   1. All SIF images are already built (see build-images.sh).
#   2. The env file has been populated with real secrets.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
ENV_FILE="${ENV_FILE:-env/prometheus.env}"
SIF_DIR="${SIF_DIR:-sif}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENV_FILE="$2"; shift 2 ;;
    --sif-dir)  SIF_DIR="$2";  shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE"
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

# ---------------------------------------------------------------------------
# Helper: require a variable is non-empty
# ---------------------------------------------------------------------------
require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: $name is not set in $ENV_FILE"
    exit 1
  fi
}

require_var LITELLM_DB_PASSWORD
require_var LITELLM_MASTER_KEY
require_var REDIS_PASSWORD
require_var AGENT_SECRET
require_var CHAINLIT_AUTH_SECRET
require_var ANTHROPIC_API_KEY

# ---------------------------------------------------------------------------
# Create data directories on the host
# ---------------------------------------------------------------------------
mkdir -p \
  "$PGDATA_DIR" \
  "$PGRUN_DIR" \
  "$REDIS_DATA_DIR" \
  "$SHARED_DIR" \
  "$OSTI_MODEL_CACHE" \
  "$HF_CACHE" \
  "$TORCH_CACHE"

# ---------------------------------------------------------------------------
# Common env flags passed to every agent instance
# ---------------------------------------------------------------------------
COMMON_APPTAINER_OPTIONS=(
  --containall
  --cleanenv
  --no-home
  --env LITELLM_URL="$LITELLM_URL"
  --env LITELLM_MASTER_KEY="$LITELLM_MASTER_KEY"
  --env REDIS_URL="$REDIS_URL"
  --env REDIS_PASSWORD="$REDIS_PASSWORD"
  --env ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
  --env MODEL_NAME="$MODEL_NAME"
  --env AGENT_SECRET="$AGENT_SECRET"
  --env AGENT_SECRET_REQUIRED="$AGENT_SECRET_REQUIRED"
  --env CA_BUNDLE="$CA_BUNDLE"
)

# Shared volume bind flag (appended to most agents)
SHARED_BIND="--bind ${SHARED_DIR}:/app/shared"

# ---------------------------------------------------------------------------
# Helper: start an instance if not already running
# ---------------------------------------------------------------------------
start_instance() {
  local name="$1"
  local sif="$2"
  shift 2
  # remaining args are extra --env / --bind flags

  if apptainer instance list | grep -q "^${name} "; then
    echo "[start] Instance '$name' is already running — skipping."
    return
  fi
  echo "[start] Starting instance: $name"
  set -x
    #--writable-tmpfs \
  apptainer instance run \
    "${COMMON_APPTAINER_OPTIONS[@]}" \
    "$@" \
    "$sif" \
    "$name"
  set +x
}

# ---------------------------------------------------------------------------
# Helper: wait for a TCP port to be open
# ---------------------------------------------------------------------------
wait_for_port() {
  local host="${1:-localhost}"
  local port="$2"
  local service="$3"
  local retries="${4:-30}"
  local delay="${5:-2}"
  echo "[wait] Waiting for $service on $host:$port ..."
  for i in $(seq 1 "$retries"); do
    if nc -z "$host" "$port" 2>/dev/null; then
      echo "[wait] $service is up."
      return 0
    fi
    sleep "$delay"
  done
  echo "ERROR: $service did not come up on $host:$port after $((retries * delay))s"
  exit 1
}

# =============================================================================
# 1. PostgreSQL (litellm-db)
# =============================================================================
start_instance litellm-db "${SIF_DIR}/litellm-db.sif" \
  --env PGPORT="$PORT_LITELLM_DB" \
  --env POSTGRES_USER=litellm \
  --env POSTGRES_PASSWORD="$LITELLM_DB_PASSWORD" \
  --env POSTGRES_DB=litellm \
  --bind "${PGDATA_DIR}:/var/lib/postgresql/data" \
  --bind "${PGRUN_DIR}:/var/run/postgresql"

wait_for_port localhost "$PORT_LITELLM_DB" litellm-db

# =============================================================================
# 2. Redis
# =============================================================================
start_instance redis "${SIF_DIR}/redis.sif" \
  --env REDIS_DATA_DIR=/data \
  --env REDIS_PORT=$PORT_REDIS \
  --env REDIS_PASSWORD="$REDIS_PASSWORD" \
  --bind "${REDIS_DATA_DIR}:/data"

wait_for_port localhost "$PORT_REDIS" redis

# =============================================================================
# 3. LiteLLM 
# =============================================================================
DATABASE_URL="postgresql://litellm:${LITELLM_DB_PASSWORD}@localhost:${PORT_LITELLM_DB}/litellm"
LITELLM_LOCAL_URL="localhost"

start_instance litellm "${SIF_DIR}/litellm.sif" \
  --env DATABASE_URL="$DATABASE_URL" \
  --env PORT_LITELLM="$PORT_LITELLM" \
  --env LITELLM_URL="$LITELLM_LOCAL_URL" \
  --bind "../litellm_config.yaml:/app/config.yaml"

wait_for_port localhost "$PORT_LITELLM" litellm 40 3

# =============================================================================
# 4. Client agent
# =============================================================================
start_instance client-agent "${SIF_DIR}/client-agent.sif" \
  $SHARED_BIND \
  --env AGENT_PORT="$PORT_CLIENT_AGENT" \
  --env CLIENT_AGENT_URL="$CLIENT_AGENT_URL"

wait_for_port localhost "$PORT_CLIENT_AGENT" client-agent 20 3

# =============================================================================
# 5. Specialist agents (order doesn't matter; all depend only on litellm/redis)
# =============================================================================
declare -A AGENTS=(
  [corrosion-agent]="${SIF_DIR}/corrosion-agent.sif|${PORT_CORROSION_AGENT}"
  [radiation-agent]="${SIF_DIR}/radiation-agent.sif|${PORT_RADIATION_AGENT}"
  [thermal-agent]="${SIF_DIR}/thermal-agent.sif|${PORT_THERMAL_AGENT}"
  [data-agent]="${SIF_DIR}/data-agent.sif|${PORT_DATA_AGENT}"
  [form-filler-agent]="${SIF_DIR}/form-filler-agent.sif|${PORT_FORM_FILLER_AGENT}"
  [artifact-debug-agent]="${SIF_DIR}/artifact-debug-agent.sif|${PORT_ARTIFACT_DEBUG_AGENT}"
  [synthesis-agent]="${SIF_DIR}/synthesis-agent.sif|${PORT_SYNTHESIS_AGENT}"
)

for agent_name in "${!AGENTS[@]}"; do
  IFS='|' read -r sif port <<< "${AGENTS[$agent_name]}"
  start_instance "$agent_name" "$sif" \
    --env AGENT_PORT="$port" \
    $SHARED_BIND
done

## osti has extra model-cache bind mounts
#start_instance osti-research-agent "${SIF_DIR}/osti-research-agent.sif" \
#  --env AGENT_PORT="$PORT_OSTI_RESEARCH_AGENT" \
#  $SHARED_BIND \
#  --bind "${OSTI_MODEL_CACHE}:/root/.cache/datalab" \
#  --bind "${HF_CACHE}:/root/.cache/huggingface" \
#  --bind "${TORCH_CACHE}:/root/.cache/torch"

# =============================================================================
# 6. Chainlit frontend
# =============================================================================
start_instance chainlit-frontend "${SIF_DIR}/chainlit-frontend.sif" \
  $SHARED_BIND \
  --bind ${FRONTEND_DATA_DIR}:/app/.files \
  --env PORT="$PORT_CHAINLIT" \
  --env CLIENT_AGENT_URL="$CLIENT_AGENT_URL" \
  --env CHAINLIT_AUTH_SECRET="$CHAINLIT_AUTH_SECRET"

wait_for_port localhost "$PORT_CHAINLIT" chainlit-frontend 20 3

# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Prometheus Platform is UP"
echo "  Chainlit UI  →  http://localhost:${PORT_CHAINLIT}"
echo "  LiteLLM UI   →  http://localhost:${PORT_LITELLM}"
echo "============================================================"

apptainer instance list

