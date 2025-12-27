#!/usr/bin/env python3
"""CLI que replica el proceso de `process_video` en `server-gpu.py`.

Realiza los pasos:
 1) Ignora ficheros con "-optimized" en el nombre.
 2) Reparar: copia streams con `-c copy` -> `_repaired.mkv`.
 3) Reducir: recodifica con `h264_nvenc`, `-b:v 2M`, escala 1280x720 -> `_reduced.mkv`.
 4) Optimizar para streaming: `-cq 27 -b:v 800k -r 30 -movflags faststart` -> `-optimized.mkv`.
 5) Validar duración con `ffprobe` (<= 2s de diferencia).
 6) Elimina original e intermedios si todo correcto.

Uso: python -m optimize_video -i input_video -o /ruta/salida
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List


valid_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}
history: List[dict] = []


def run(cmd: List[str]) -> None:
    print("Ejecutando:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def get_video_duration(video_path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def process_video(video_path: str, output_dir: str) -> None:
    global history

    if "-optimized" in video_path:
        print("Ignorado (ya optimizado):", video_path)
        return

    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)

    base_root = os.path.splitext(os.path.basename(video_path))[0]
    repaired = os.path.join(output_dir, base_root + "_repaired.mkv")
    reduced = os.path.join(output_dir, base_root + "_reduced.mkv")
    optimized = os.path.join(output_dir, base_root + "-optimized.mkv")

    try:
        # Paso 1: Reparar (copiar streams)
        run([
            "ffmpeg",
            "-err_detect",
            "ignore_err",
            "-i",
            video_path,
            "-c",
            "copy",
            repaired,
        ])

        # Paso 2: Reducir tamaño
        run([
            "ffmpeg",
            "-i",
            repaired,
            "-c:v",
            "h264_nvenc",
            "-preset",
            "fast",
            "-b:v",
            "2M",
            "-vf",
            "scale=1280:720",
            "-c:a",
            "aac",
            "-ac",
            "2",
            reduced,
        ])

        # Paso 3: Optimizar para streaming
        run([
            "ffmpeg",
            "-i",
            reduced,
            "-c:v",
            "h264_nvenc",
            "-preset",
            "fast",
            "-cq",
            "27",
            "-b:v",
            "800k",
            "-r",
            "30",
            "-vf",
            "scale=1280:720",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-movflags",
            "faststart",
            "-gpu",
            "0",
            optimized,
        ])

        # Paso 4: Validar duración
        orig_dur = get_video_duration(video_path)
        opt_dur = get_video_duration(optimized)
        if abs(orig_dur - opt_dur) > 2:
            raise ValueError("La duración del archivo optimizado no coincide con el original")

        # Eliminar ficheros originales e intermedios
        try:
            os.remove(video_path)
        except Exception:
            pass
        for f in (repaired, reduced):
            try:
                os.remove(f)
            except Exception:
                pass

        history.append({"name": os.path.basename(video_path), "status": "Procesado correctamente"})
        print("Procesado correctamente:", optimized)

    except Exception as e:
        history.append({"name": os.path.basename(video_path), "status": f"Error: {e}"})
        print("Error procesando:", e, file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Procesa un video replicando server-gpu.py")
    parser.add_argument("-i", "--input", required=True, help="Fichero de entrada (mp4/mkv/avi/...) ")
    parser.add_argument("-o", "--output", required=True, help="Carpeta de salida (se crean los intermedios ahí)")
    args = parser.parse_args()

    if os.path.splitext(args.input)[1].lower() not in valid_extensions:
        print("Extensión no válida.", file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.output, exist_ok=True)

    try:
        process_video(args.input, args.output)
    except FileNotFoundError:
        print(f"Fichero no encontrado: {args.input}", file=sys.stderr)
        sys.exit(2)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
