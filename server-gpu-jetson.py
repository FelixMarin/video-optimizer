#!/usr/bin/env python3
"""
Servidor Jetson GPU — versión GStreamer

Procesa vídeos usando:
- Decodificación hardware: nvv4l2decoder
- Conversión hardware: nvvidconv
- Encode software: x264enc
- Pipelines GStreamer estables (sin NVMM en el encoder)

Estructura similar a server-gpu.py, pero:
- Reemplaza NVENC por GStreamer (HW decode + SW encode).
- Expone video_info, status_raw y log_line para el frontend.
"""

from flask import Flask, request, jsonify, render_template
import os
import threading
import subprocess
from pathlib import Path
import contextlib

app = Flask(__name__)

current_video = None
current_step = 0
history = []

# Datos para el frontend
video_info = {}
status_raw = ""  # Últimas líneas de log de ffmpeg/gst

valid_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}


# ------------------------------
# Helpers
# ------------------------------

def run(cmd: list[str]):
    """
    Ejecuta un comando capturando salida en tiempo real.
    """
    global status_raw

    print("Ejecutando:", " ".join(cmd))
    
    # Usar Popen para capturar stdout y stderr en tiempo real
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Combinar stderr en stdout
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    last_lines = []
    try:
        # Leer la salida línea por línea
        for line in proc.stdout:
            if line:
                line = line.rstrip("\n")
                print(line)
                last_lines.append(line)
                
                # Limitar a las últimas 50 líneas
                if len(last_lines) > 50:
                    last_lines.pop(0)
                
                status_raw = "\n".join(last_lines)
    except Exception as e:
        print(f"Error leyendo salida: {e}")
    finally:
        ret = proc.wait()
        if ret != 0:
            raise subprocess.CalledProcessError(ret, cmd)


def get_video_duration(path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def choose_demux_mux(path: str):
    ext = Path(path).suffix.lower()
    if ext == ".mkv":
        return "matroskademux", "matroskamux"
    return "qtdemux", "mp4mux"


def extract_video_info(path: str) -> dict:
    """Extrae info básica del vídeo para la tabla 'Información del video original'."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,format_name",
                "-show_streams",
                "-of", "default=noprint_wrappers=1",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        info = {"name": os.path.basename(path)}
        vcodec = None
        acodec = None
        width = None
        height = None

        for line in lines:
            if line.startswith("duration="):
                info["duration"] = line.split("=", 1)[1] + " sec"
            elif line.startswith("size="):
                try:
                    sz = int(line.split("=", 1)[1])
                    info["size"] = f"{sz / (1024 * 1024):.2f} MB"
                except ValueError:
                    pass
            elif line.startswith("format_name="):
                info["formats"] = line.split("=", 1)[1]
            elif line.startswith("codec_type=video"):
                # codec_name vendrá en otra línea
                pass
            elif line.startswith("codec_type=audio"):
                pass
            elif line.startswith("codec_name="):
                name = line.split("=", 1)[1]
                if vcodec is None:
                    vcodec = name
                elif acodec is None:
                    acodec = name
            elif line.startswith("width="):
                width = line.split("=", 1)[1]
            elif line.startswith("height="):
                height = line.split("=", 1)[1]

        if width and height:
            info["resolution"] = f"{width}x{height}"
        if vcodec:
            info["vcodec"] = vcodec
        if acodec:
            info["acodec"] = acodec

        # Campo genérico
        info.setdefault("codec", vcodec or "")
        return info
    except Exception:
        return {}


# ------------------------------
# Pipeline GStreamer
# ------------------------------

def gst_reduce(repaired: str, reduced: str, reduce_kbps: int):
    demux, mux = choose_demux_mux(repaired)

    pipeline = [
        "gst-launch-1.0",
        "-v",

        "filesrc", f"location={repaired}",
        "!", demux, "name=demux",

        # Declarar muxer antes de usar mux.
        mux, "name=mux", "!", "progressreport", "!", "filesink", f"location={reduced}",

        # VIDEO → mux.
        "demux.video_0", "!", "queue", "!",
        "h264parse", "!",
        "nvv4l2decoder", "!",
        "nvvidconv", "!",
        "video/x-raw,format=I420,width=1280,height=720", "!",
        "x264enc",
        f"bitrate={reduce_kbps}",
        "speed-preset=superfast",
        "tune=zerolatency",
        "key-int-max=60",
        "!", "h264parse", "!", "mux.",

        # AUDIO → mux.
        "demux.audio_0", "!", "queue", "!",
        "decodebin", "!", "audioconvert", "!",
        "avenc_aac", "!", "aacparse", "!", "mux.",
    ]

    run(pipeline)


def gst_optimize(reduced: str, optimized: str, opt_kbps: int):
    demux, mux = choose_demux_mux(reduced)

    pipeline = [
        "gst-launch-1.0",
        "-v",

        "filesrc", f"location={reduced}",
        "!", demux, "name=demux",

        # Declarar muxer antes de usar mux.
        # CORRECCIÓN: Cambiar 'reduced' por 'optimized' en el filesink
        mux, "name=mux", "!", "progressreport", "!", "filesink", f"location={optimized}",  # <-- CAMBIO AQUÍ

        # VIDEO → mux.
        "demux.video_0", "!", "queue", "!",
        "h264parse", "!",
        "nvv4l2decoder", "!",
        "nvvidconv", "!",
        "video/x-raw,format=I420,width=1280,height=720", "!",
        "x264enc",
        f"bitrate={opt_kbps}",
        "speed-preset=superfast",
        "tune=zerolatency",
        "key-int-max=60",
        "!", "h264parse", "!", "mux.",

        # AUDIO → mux.
        "demux.audio_0", "!", "queue", "!",
        "decodebin", "!", "audioconvert", "!",
        "avenc_aac", "!", "aacparse", "!", "mux.",
    ]

    run(pipeline)

# ------------------------------
# Procesamiento principal
# ------------------------------

def process_video(video_path: str):
    global current_video, current_step, history, video_info, status_raw

    if "-optimized" in video_path:
        return

    current_video = os.path.basename(video_path)
    base = Path(video_path).stem

    dirname = os.path.dirname(video_path) or "."
    repaired = os.path.join(dirname, f"{base}_repaired.mp4")
    reduced = os.path.join(dirname, f"{base}_reduced.mp4")
    optimized = os.path.join(dirname, f"{base}-optimized.mp4")

    try:
        # 1) Reparar (remux limpio)
        current_step = 1
        run([
            "ffmpeg",
            "-err_detect", "ignore_err",
            "-i", video_path,
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-y",
            repaired,
        ])

        # VERIFICAR que repaired existe y tiene tamaño
        if not os.path.exists(repaired) or os.path.getsize(repaired) == 0:
            raise Exception(f"Archivo reparado no creado o vacío: {repaired}")

        # Info para la UI
        video_info = extract_video_info(repaired)

        # 2) Reducir (GStreamer)
        current_step = 2
        gst_reduce(repaired, reduced, reduce_kbps=2000)
        
        # VERIFICAR que reduced existe y tiene tamaño
        if not os.path.exists(reduced) or os.path.getsize(reduced) == 0:
            raise Exception(f"Archivo reducido no creado o vacío: {reduced}")
            
        # OPCIONAL: Verificar con ffprobe que es válido
        try:
            check_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", reduced],
                capture_output=True,
                text=True,
                timeout=5
            )
            if check_result.returncode != 0:
                raise Exception(f"Archivo reducido no es válido: {check_result.stderr[:200]}")
        except:
            pass  # Si falla ffprobe, continuamos de todos modos

        # 3) Optimizar (GStreamer)
        current_step = 3
        # --- AÑADE ESTAS LÍNEAS PARA DEPURAR ---
        print(f"[DEBUG] Archivo reducido para optimizar: {reduced}")
        print(f"[DEBUG] Archivo optimizado de salida: {optimized}")
        print(f"[DEBUG] ¿Son diferentes? {reduced != optimized}")
        gst_optimize(reduced, optimized, opt_kbps=800)

        # 4) Validar duración
        current_step = 4
        orig = get_video_duration(video_path)
        opt = get_video_duration(optimized)

        if abs(orig - opt) > 2:
            raise ValueError(f"Duración incorrecta (>2s): original={orig}s, optimizado={opt}s")

        # 5) Limpiar
        with contextlib.suppress(Exception):
            os.remove(video_path)
        with contextlib.suppress(Exception):
            os.remove(repaired)
        with contextlib.suppress(Exception):
            os.remove(reduced)

        history.append({"name": current_video, "status": "Procesado correctamente"})

    except Exception as e:
        history.append({"name": current_video, "status": f"Error: {e}"})

    finally:
        current_video = None
        current_step = 0


def process_folder(folder_path: str):
    global history
    history = []

    for root, _, files in os.walk(folder_path):
        for f in files:
            if Path(f).suffix.lower() in valid_extensions:
                process_video(os.path.join(root, f))


# ------------------------------
# Rutas Flask
# ------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    if not data or "folder" not in data:
        return jsonify({"error": "Ruta no proporcionada"}), 400

    folder = data["folder"]
    if not os.path.exists(folder):
        return jsonify({"error": "La ruta no existe"}), 400

    threading.Thread(target=process_folder, args=(folder,)).start()

    return jsonify({"message": f"Procesando carpeta: {folder}"}), 200


@app.route("/status", methods=["GET"])
def status():
    # log_line: última línea de status_raw para el icono de estado
    last_line = ""
    if status_raw:
        lines = status_raw.strip().splitlines()
        if lines:
            last_line = lines[-1]

    return jsonify({
        "current_file": current_video,
        "current_step": current_step,
        "history": history,
        "video_info": video_info,
        "status_raw": status_raw,
        "log_line": last_line,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
