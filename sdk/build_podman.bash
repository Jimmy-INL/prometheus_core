#!/bin/bash
podman login mooseharbor.hpc.inl.gov
podman build --platform linux/amd64 -t mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api:latest .
