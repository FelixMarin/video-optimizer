#!/usr/bin/env bash

# Uso:
#   ./run_server.sh server-gpu-jetson
#   ./run_server.sh server-gpu
#   ./run_server.sh server
#   ./run_server.sh server-gpu-ray

SERVER="$1"

if [ -z "$SERVER" ]; then
    echo "Uso: ./run_server.sh <server>"
    exit 1
fi

SCRIPT="${SERVER}.py"

# Detectar arquitectura
ARCH=$(uname -m)

if [[ "$ARCH" == "aarch64" ]]; then
    # Jetson
    COMPOSE_FILE="docker-compose.jetson.yml"
    IMAGE="video-optimizer-jetson:latest"
else
    # x86_64 CUDA
    COMPOSE_FILE="docker-compose.cuda.yml"
    IMAGE="video-optimizer-cuda:latest"
fi

echo "Arquitectura detectada: $ARCH"
echo "Usando compose: $COMPOSE_FILE"
echo "Usando imagen: $IMAGE"
echo "Ejecutando servidor: $SCRIPT"

docker compose -f "$COMPOSE_FILE" run --rm app python "$SCRIPT"
