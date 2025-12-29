#!/usr/bin/env python3
"""CLI para Jetson (JetPack 6).

Herramienta para optimizar vídeos (HW decode + SW encode) y arrancar servidores
incluidos con `--server`.
"""

import argparse
import contextlib
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Extensiones válidas de vídeo (usadas por la comprobación básica)
valid_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}

# Estado histórico de procesados
history = []


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Ejecuta un comando (lista de argumentos) y lanza si hay error.

    El proyecto usa listas en todas las llamadas; rechazar cadenas evita
    problemas con `shell=True`.
    """
    return subprocess.run(cmd, check=True)


def gst_has(plugin: str) -> bool:
    """Comprueba si un plugin de GStreamer está disponible."""
    gst_exe = shutil.which("gst-inspect-1.0")
    if not gst_exe:
        return False
    try:
        subprocess.run([gst_exe, plugin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def is_jetson() -> bool:
    """Heurística simple para detectar Jetson (L4T)."""
    if Path("/etc/nv_tegra_release").exists():
        return True
    try:
        return platform.machine().startswith("aarch64")
    except Exception:
        return False


def get_video_duration(video_path: str) -> float:
    """Devuelve la duración del vídeo en segundos usando ffprobe."""
    ffprobe_exe = shutil.which("ffprobe")
    if not ffprobe_exe:
        return 0.0
    try:
        result = subprocess.run(
            [
                ffprobe_exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 0.0


def choose_gst_audio_encoder() -> str:
    """Selecciona encoder de audio disponible para GStreamer."""
    for p in ("avenc_aac", "voaacenc"):
        if gst_has(p):
            return p
    return "avenc_aac"


def choose_gst_sw_h264_encoder() -> str:
    """Selecciona encoder H.264 por software disponible en GStreamer."""
    # Encoder software para JetPack 6: preferimos x264enc, luego avenc_h264
    for p in ("x264enc", "avenc_h264"):
        if gst_has(p):
            return p
    return "x264enc"


def choose_demux_mux(path: str) -> tuple[str, str]:
    """Devuelve (demux, mux) apropiados según la extensión del fichero."""
    ext = Path(path).suffix.lower()
    if ext == ".mkv":
        return "matroskademux", "matroskamux"
    # por defecto MP4
    return "qtdemux", "mp4mux"


def process_video(
    video_path: str,
    output_dir: str,
    *,
    reduce_bitrate: str = "2M",
    opt_bitrate: str = "800k",
    backend: str = "auto",
) -> None:
    global history

    if "-optimized" in video_path:
        logger.info("Ignorado (ya optimizado): %s", video_path)
        return

    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(video_path)

    base_root = src.stem
    outdir = Path(output_dir)
    repaired = str(outdir / f"{base_root}_repaired.mp4")
    reduced = str(outdir / f"{base_root}_reduced.mp4")
    optimized = str(outdir / f"{base_root}-optimized.mp4")

    try:
        # Paso 1: Reparar (remux limpio)
        run([
            "ffmpeg",
            "-err_detect", "ignore_err",
            "-i", video_path,
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-movflags", "+faststart",
            repaired,
        ])

        use_gst = backend == "gstreamer" or (backend == "auto" and is_jetson())

        if use_gst:
            logger.info("Usando GStreamer (Jetson: decode HW, encode CPU)")

            demux, mux = choose_demux_mux(repaired)

            # Convertir bitrates
            try:
                reduce_k = int(float(reduce_bitrate.rstrip("M")) * 1000)
            except ValueError:
                reduce_k = 2000
            try:
                opt_k = int(float(opt_bitrate.rstrip("k")))
            except ValueError:
                opt_k = 800

            # ============================
            #   GStreamer REDUCE
            #   Decode HW → Encode CPU
            # ============================
            gst_reduce = [
                "gst-launch-1.0",

                "filesrc", f"location={repaired}",
                "!", demux, "name=demux",

                mux, "name=mux", "!", "filesink", f"location={reduced}",

                # VIDEO: HW decode → CPU encode
                "demux.video_0", "!", "queue", "!",
                "h264parse", "!",
                "nvv4l2decoder", "!",
                "nvvidconv", "!",
                "video/x-raw,format=I420,width=1280,height=720", "!",
                "x264enc",
                f"bitrate={reduce_k}",
                "speed-preset=superfast",
                "tune=zerolatency",
                "key-int-max=60",
                "!", "h264parse", "!", "mux.",

                # AUDIO: SW
                "demux.audio_0", "!", "queue", "!",
                "decodebin", "!", "audioconvert", "!",
                "avenc_aac", "!", "aacparse", "!", "mux.",
            ]

            run(gst_reduce)

            # ============================
            #   GStreamer OPTIMIZE
            #   Decode HW → Encode CPU
            # ============================
            gst_opt = [
                "gst-launch-1.0",

                "filesrc", f"location={reduced}",
                "!", demux, "name=demux",

                mux, "name=mux", "!", "filesink", f"location={optimized}",

                # VIDEO
                "demux.video_0", "!", "queue", "!",
                "h264parse", "!",
                "nvv4l2decoder", "!",
                "nvvidconv", "!",
                "video/x-raw,format=I420,width=1280,height=720", "!",
                "x264enc",
                f"bitrate={opt_k}",
                "speed-preset=superfast",
                "tune=zerolatency",
                "key-int-max=60",
                "!", "h264parse", "!", "mux.",

                # AUDIO
                "demux.audio_0", "!", "queue", "!",
                "decodebin", "!", "audioconvert", "!",
                "avenc_aac", "!", "aacparse", "!", "mux.",
            ]

            run(gst_opt)

        else:
            # FFmpeg backend (x86)
            logger.info("Usando backend FFmpeg (sin GStreamer).")

            run([
                "ffmpeg",
                "-hwaccel", "cuda",
                "-i", repaired,
                "-c:v", "h264_nvenc",
                "-preset", "fast",
                "-b:v", reduce_bitrate,
                "-vf", "scale=1280:720",
                "-c:a", "aac",
                "-ac", "2",
                reduced,
            ])

            run([
                "ffmpeg",
                "-hwaccel", "cuda",
                "-i", reduced,
                "-c:v", "h264_nvenc",
                "-preset", "fast",
                "-b:v", opt_bitrate,
                "-vf", "scale=1280:720",
                "-c:a", "aac",
                "-ac", "2",
                "-movflags", "faststart",
                optimized,
            ])

        # Validación
        orig_dur = get_video_duration(video_path)
        opt_dur = get_video_duration(optimized)
        logger.info("Duración original: %.2fs, optimizado: %.2fs", orig_dur, opt_dur)

        if abs(orig_dur - opt_dur) > 2:
            raise ValueError("Duración incorrecta (>2s)")

        # Limpiar
        for f in (video_path, repaired, reduced):
            with contextlib.suppress(Exception):
                Path(f).unlink(missing_ok=True)

        history.append({"name": Path(video_path).name, "status": "Procesado correctamente"})
        logger.info("Procesado correctamente: %s", optimized)

    except Exception as e:
        history.append({"name": Path(video_path).name, "status": f"Error: {e}"})
        logger.exception("Error procesando %s", video_path)
        raise

def main() -> None:
    """Punto de entrada CLI: parsea argumentos y lanza procesamiento o servidor."""
    parser = argparse.ArgumentParser(
        description=(
            "Optimiza un vídeo usando HW decode (Jetson) + SW encode (x264)."
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Fichero de entrada (mp4/mkv/avi...)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Carpeta de salida",
    )
    parser.add_argument(
        "--server",
        choices=["server", "server-gpu", "server-gpu-ray"],
        help=(
            "Ejecutar uno de los servidores incluidos en el repo dentro del contenedor"
            " (ej.: --server server-gpu)"
        ),
    )
    parser.add_argument(
        "--reduce-bitrate",
        default="2M",
        help="Bitrate para el paso de reducción (por defecto: 2M)",
    )
    parser.add_argument(
        "--opt-bitrate",
        default="800k",
        help="Bitrate para el paso de optimización (por defecto: 800k)",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "ffmpeg", "gstreamer"],
        default="auto",
        help=(
            "Backend: 'auto' usa GStreamer en Jetson, FFmpeg en el resto."
        ),
    )
    args = parser.parse_args()

    # Si se solicita arrancar un servidor, ejecutarlo y salir (ignora otras opciones)
    if getattr(args, "server", None):
        server = args.server
        script_path = Path.cwd() / f"{server}.py"
        if not script_path.exists():
            logger.exception("Error: no se encontró el script del servidor: %s", script_path)
            sys.exit(2)
        try:
            subprocess.run([sys.executable, str(script_path)], check=True)
        except subprocess.CalledProcessError:
            logger.exception("El servidor %s finalizó con error", server)
            sys.exit(1)
        return

    if Path(args.input).suffix.lower() not in valid_extensions:
        logger.error("Extensión no válida: %s", args.input)
        sys.exit(2)

    Path(args.output).mkdir(parents=True, exist_ok=True)

    try:
        process_video(
            args.input,
            args.output,
            reduce_bitrate=args.reduce_bitrate,
            opt_bitrate=args.opt_bitrate,
            backend=args.backend,
        )
    except FileNotFoundError:
        logger.exception("Fichero no encontrado: %s", args.input)
        sys.exit(2)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
