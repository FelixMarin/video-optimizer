#!/bin/bash

# --- Validación de parámetros ---
if [ "$#" -ne 2 ]; then
    echo "Uso: $0 /ruta/al/video.mp4 /ruta/de/salida"
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_DIR="$2"

# --- Comprobaciones ---
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: El archivo de entrada no existe: $INPUT_FILE"
    exit 1
fi

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: La carpeta de salida no existe: $OUTPUT_DIR"
    exit 1
fi

# --- Rutas absolutas ---
INPUT_FILE_ABS="$(realpath "$INPUT_FILE")"
INPUT_DIR_ABS="$(dirname "$INPUT_FILE_ABS")"
OUTPUT_DIR_ABS="$(realpath "$OUTPUT_DIR")"

# --- Nombre del archivo dentro del contenedor ---
INPUT_BASENAME="$(basename "$INPUT_FILE_ABS")"

# --- Ejecución del contenedor ---
docker run --rm -it \
    -v "$INPUT_DIR_ABS":/app/inputs \
    -v "$OUTPUT_DIR_ABS":/app/outputs \
    video-optimezer:latest \
    -i "/app/inputs/$INPUT_BASENAME" \
    -o "/app/outputs"
