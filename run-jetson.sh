#!/usr/bin/env bash
set -euo pipefail

# Ejecuta `optimize_video` en Jetson usando GStreamer y guarda logs
LOGDIR="./logs"
mkdir -p "$LOGDIR"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTLOG="$LOGDIR/run-jetson-${TIMESTAMP}.log"

echo "Registro: $OUTLOG"

echo "== gst-inspect (h264) ==" | tee -a "$OUTLOG"
gst-inspect-1.0 | grep h264 2>/dev/null | tee -a "$OUTLOG"
echo "== gst-inspect (aac) ==" | tee -a "$OUTLOG"
gst-inspect-1.0 | grep aac 2>/dev/null | tee -a "$OUTLOG"

INPUT=${1:-inputs/el_cantico_final.mp4}
OUTPUT_DIR=${2:-outputs}

echo "Ejecutando optimize_video con backend=gstreamer" | tee -a "$OUTLOG"
python3 -m optimize_video -i "$INPUT" -o "$OUTPUT_DIR" --backend gstreamer 2>&1 | tee -a "$OUTLOG"

echo "Fin. Revisa $OUTLOG" 
