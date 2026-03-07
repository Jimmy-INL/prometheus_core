#!/bin/bash
log_dir=/hpc-common/systems/c500-prometheus/logs

# This is only needed for okta auth, nothing else
# echo "Starting auth db in a screen..."
# cd /hpc-common/systems/c500-prometheus/platform_db
# screen -d -m -L -Logfile ${log_dir}/platform_auth_db.log -S prometheus-auth-db bash -c "bash postgres_start.bash"

echo "Starting backend in a screen..."
cd /hpc-common/systems/c500-prometheus/prometheus_platform/backend
screen -d -m -L -Logfile ${log_dir}/platform_backend.log -S prometheus-backend bash -c "make run"

echo "Starting frontend in a screen..."
cd /hpc-common/systems/c500-prometheus/prometheus_platform/frontend
screen -d -m -L -Logfile ${log_dir}/platform_frontend.log -S prometheus-frontend bash -c "make run"

