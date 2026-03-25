#!/bin/bash
source env/prometheus.env
apptainer exec \
    --env REDIS_DATA_DIR=/data \
    --bind "${REDIS_DATA_DIR}:/data" \
    sif/redis.sif \
    redis-cli -h localhost -p ${PORT_REDIS} -a ${REDIS_PASSWORD}
