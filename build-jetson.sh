#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=${1:-video-optimezer:jetson}
DOCKERFILE=${2:-Dockerfile.jetson}

echo "Construyendo imagen Jetson: $IMAGE_NAME usando $DOCKERFILE"
docker build -f "$DOCKERFILE" -t "$IMAGE_NAME" .
echo "Imagen creada: $IMAGE_NAME"
