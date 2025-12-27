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
import platform


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


def is_jetson() -> bool:
    # Detecta una Jetson examinando el archivo de release o la arquitectura
    try:
        if platform.machine() == "aarch64":
            if os.path.exists("/etc/nv_tegra_release"):
                return True
    except Exception:
        pass
    return False


def gst_has(plugin: str) -> bool:
    try:
        subprocess.run(["gst-inspect-1.0", plugin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def choose_gst_video_encoder() -> str:
    # Prefer hardware-accelerated encoders commonly available on Jetson
    for p in ("omxh264enc", "nvh264enc", "avenc_h264_omx"):
        if gst_has(p):
            return p
    return "avenc_h264_omx"


def choose_gst_audio_encoder() -> str:
    for p in ("avenc_aac", "faac", "voaacenc"):
        if gst_has(p):
            return p
    return "avenc_aac"


def process_video(video_path: str, output_dir: str, *, cq: int = 27, crf: int = 23, reduce_bitrate: str = "2M", opt_bitrate: str = "800k", gpu: str = "0", backend: str = "auto") -> None:
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
        # Si se selecciona backend GStreamer (o auto detectado Jetson), usar gst-launch-1.0
        use_gst = False
        if backend == "gstreamer":
            use_gst = True
        elif backend == "auto" and is_jetson():
            use_gst = True

        if use_gst:
            # Elige encoders disponibles en el sistema
            video_enc = choose_gst_video_encoder()
            audio_enc = choose_gst_audio_encoder()
            print(f"Usando GStreamer video encoder: {video_enc}, audio encoder: {audio_enc}")

            # Convertir bitrates a valores apropiados para los plugins
            try:
                reduce_k = int(float(reduce_bitrate.rstrip('M')) * 1000)
            except Exception:
                reduce_k = 2000
            try:
                opt_k = int(float(opt_bitrate.rstrip('k')))
            except Exception:
                opt_k = 800

            # Paso 2 (reduce) con GStreamer: demux -> decode -> nvvidconv -> encoder -> mp4mux
            gst_reduce = [
                "gst-launch-1.0",
                "filesrc", f"location={repaired}",
                "!", "qtdemux", "name=demux",
                "demux.video_0", "!", "queue", "!", "decodebin", "!", "nvvidconv", "!",
                "video/x-raw(memory:NVMM),format=I420", "!", video_enc, f"bitrate={reduce_k}", "!",
                "h264parse", "!", "mp4mux", "name=mux", "!", f"filesink location={reduced}",
                "demux.audio_0", "!", "queue", "!", "decodebin", "!", "audioconvert", "!", audio_enc, "!", "aacparse", "!", "mux.",
            ]
            run(gst_reduce)

            # Paso 3 (optimizar) con GStreamer: menor bitrate y target 30fps
            gst_opt = [
                "gst-launch-1.0",
                "filesrc", f"location={reduced}",
                "!", "qtdemux", "name=demux",
                "demux.video_0", "!", "queue", "!", "decodebin", "!", "nvvidconv", "!",
                "video/x-raw(memory:NVMM),format=I420", "!", video_enc, f"bitrate={opt_k}", "!",
                "h264parse", "!", "video/x-h264,profile=baseline", "!", "mp4mux", "name=mux", "!", f"filesink location={optimized}",
                "demux.audio_0", "!", "queue", "!", "decodebin", "!", "audioconvert", "!", audio_enc, "!", "aacparse", "!", "mux.",
            ]
            run(gst_opt)

        else:
            # Usar ffmpeg NVENC (normalmente en máquinas x86_64 con NVIDIA)
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
                reduce_bitrate,
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
                str(cq),
                "-b:v",
                opt_bitrate,
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
                str(gpu),
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
    parser.add_argument("--cq", type=int, default=27, help="Valor CQ para NVENC en paso de optimización (por defecto: 27)")
    parser.add_argument("--crf", type=int, default=23, help="Valor CRF para libx264 si se utiliza (por defecto: 23)")
    parser.add_argument("--reduce-bitrate", default="2M", help="Bitrate para el paso de reducción (por defecto: 2M)")
    parser.add_argument("--opt-bitrate", default="800k", help="Bitrate para el paso de optimización (por defecto: 800k)")
    parser.add_argument("--gpu", default="0", help="ID de GPU para pasar a ffmpeg (por defecto: 0)")
    parser.add_argument("--backend", choices=["auto", "ffmpeg", "gstreamer"], default="auto", help="Backend a usar: 'auto' detecta Jetson, 'gstreamer' fuerza gst-launch-1.0, 'ffmpeg' fuerza ffmpeg/NVENC")
    args = parser.parse_args()

    if os.path.splitext(args.input)[1].lower() not in valid_extensions:
        print("Extensión no válida.", file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.output, exist_ok=True)

    try:
        process_video(args.input, args.output, cq=args.cq, crf=args.crf, reduce_bitrate=args.reduce_bitrate, opt_bitrate=args.opt_bitrate, gpu=args.gpu, backend=args.backend)
    except FileNotFoundError:
        print(f"Fichero no encontrado: {args.input}", file=sys.stderr)
        sys.exit(2)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
