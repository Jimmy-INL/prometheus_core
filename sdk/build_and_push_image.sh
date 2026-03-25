#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_REPO="${IMAGE_REPO:-${1:-}}"
IMAGE_TAG="${IMAGE_TAG:-${2:-$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)}}"
PUSH_LATEST="${PUSH_LATEST:-true}"

if [[ -z "$IMAGE_REPO" ]]; then
    echo "Usage: $0 <image-repo> [tag]"
    echo ""
    echo "Example:"
    echo "  $0 ghcr.io/my-org/prometheus-api"
    echo "  $0 registry.example.com/team/prometheus-api v0.1.0"
    exit 1
fi

cd "$SCRIPT_DIR"

echo "Building ${IMAGE_REPO}:${IMAGE_TAG}"
DOCKER_BUILDKIT=1 docker build -t "${IMAGE_REPO}:${IMAGE_TAG}" .

echo "Pushing ${IMAGE_REPO}:${IMAGE_TAG}"
docker push "${IMAGE_REPO}:${IMAGE_TAG}"

if [[ "$PUSH_LATEST" == "true" ]]; then
    echo "Tagging ${IMAGE_REPO}:latest"
    docker tag "${IMAGE_REPO}:${IMAGE_TAG}" "${IMAGE_REPO}:latest"

    echo "Pushing ${IMAGE_REPO}:latest"
    docker push "${IMAGE_REPO}:latest"
fi

echo "Done"
