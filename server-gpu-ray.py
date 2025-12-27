from flask import Flask, request, jsonify, render_template
import os
import subprocess
import ray
import logging
import threading
import tempfile
import shutil
import json
import platform
from pathlib import Path

app = Flask(__name__)
os.environ["RAY_DEDUP_LOGS"] = "0"
ray.init()

valid_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}

ultimo_resumen = None  # estado global/local del último resumen enviado

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

@ray.remote
class StatusTracker:
    def __init__(self):
        self.last_log_line = ""
        self.last_pretty_line = ""
        self.history = []                # [(video, mensaje), ...]
        self.current_video = None
        self.current_step = None
        self.progress = 0
        self.total_frames = 0
        self.current_file_path = None

    def set_video(self, name, full_path=None):
        self.current_video = name
        self.current_file_path = full_path

    def set_step(self, step):
        """Guardar el número/paso actual del pipeline."""
        self.current_step = step

    def set_progress(self, value, total_frames=0):
        """
        Actualizar progreso.
        - value: progreso actual (frames procesados, porcentaje, etc.)
        - total_frames: total estimado de frames (opcional)
        """
        self.progress = value
        if total_frames:
            self.total_frames = total_frames

    def reset_progress(self):
        """Reiniciar progreso y total de frames."""
        self.progress = 0
        self.total_frames = 0

    def set_log_line(self, line):
        """Registrar la última línea de log y la 'bonita' si aplica."""
        if line and "frames" in line:
            self.last_pretty_line = line
        self.last_log_line = line

    def add_history(self, video_name, message):
        """Añadir entrada al historial."""
        self.history.append((video_name, message))

    def clear_history(self):
        """Vaciar historial."""
        self.history = []

    def get_status(self):
        """Obtener snapshot del estado actual."""
        return {
            "current_file": self.current_video,
            "current_step": self.current_step,
            "progress": self.progress,
            "total_frames": self.total_frames,
            "log_line": self.last_pretty_line or self.last_log_line,
            "history": self.history,
            "current_file_path": self.current_file_path,
        }

status_actor = StatusTracker.options(resources={"jetson": 0}).remote()

def get_gpu_encoder():
    if Path("/usr/lib/aarch64-linux-gnu/tegra").exists():
        return "h264_nvmpi"  # Jetson
    else:
        return "h264_nvenc"  # PC con NVIDIA

def get_video_duration(video_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             video_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def get_total_frames(video_path):
    print(f"get_total_frames({video_path})")

    def probe(path):
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-analyzeduration", "100M",
                    "-probesize", "100M",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=r_frame_rate,duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=True
            )
            lines = result.stdout.strip().splitlines()
            if len(lines) >= 2:
                # Parse FPS
                try:
                    if "/" in lines[0]:
                        num, den = map(int, lines[0].split('/'))
                        fps = num / den if den != 0 else float(num)
                    else:
                        fps = float(lines[0]) if lines[0] else 0.0
                except ValueError:
                    fps = 0.0
                # Parse duration
                try:
                    duration = float(lines[1])
                except ValueError:
                    duration = 0.0
                total_frames = int(fps * duration)
                print(f"fps={fps}, dur={duration}, estimado={total_frames}")
                return total_frames
        except subprocess.CalledProcessError:
            pass
        return 0

    # Primer intento
    total_frames = probe(video_path)

    # Si falla, intentamos rehacer encabezados y volver a medir
    if total_frames == 0:
        tmp_dir = tempfile.mkdtemp()
        ext = os.path.splitext(video_path)[1]
        fixed_path = os.path.join(tmp_dir, f"fixed{ext}")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-c", "copy", "-map", "0", fixed_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
            total_frames = probe(fixed_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Valor de seguridad para que la UI no se bloquee
    if total_frames == 0:
        total_frames = 100
        print(f"⚠️  No se pudo determinar la duración real. Usando valor por defecto: {total_frames} frames.")

    return total_frames

def stream_reader(stream, stream_name, status_actor, last_line_ref, progress_ref, total_duration):
    """Lee la salida de FFmpeg línea a línea, actualiza progreso y log en el actor."""
    for raw_line in iter(stream.readline, ''):
        line = raw_line.strip()
        print(f"{line}")
        
        # Intentamos parsear el progreso 'bonito'
        resumen = parse_ffmpeg_progress(line)

        if resumen:
            # Actualizamos última línea y notificamos al actor
            last_line_ref[0] = resumen
            try:
                ray.get(status_actor.set_log_line.remote(last_line_ref[0]))
            except Exception as e:
                logging.error(f"Error enviando log al actor: {e}")
        else:
            continue

    stream.close()

def run_ffmpeg_with_progress(cmd, status_actor):
    last_line_ref = ["Esperando progreso..."]
    progress_ref = [0]
    total_duration = [0]

    if "-progress" not in cmd:
        cmd.extend(["-progress", "pipe:2", "-nostats"])

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )

    threads = [
        threading.Thread(target=stream_reader, args=(process.stderr, "STDERR", status_actor, last_line_ref, progress_ref, total_duration)),
        threading.Thread(target=stream_reader, args=(process.stdout, "STDOUT", status_actor, last_line_ref, progress_ref, total_duration)),
    ]

    for t in threads:
        t.start()

    process.wait()

    for t in threads:
        t.join()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

    return last_line_ref[0]

@ray.remote
def process_pipeline(video_path, status_actor):
    import subprocess, os, logging
    from pathlib import Path

    print(f"process_pipeline({video_path}, {status_actor})")
    last_log_line = None

    if "-optimized" in video_path:
        return

    current_name = os.path.basename(video_path)
    ray.get(status_actor.set_video.remote(current_name, video_path))
    ray.get(status_actor.set_step.remote(1))
    ray.get(status_actor.set_log_line.remote(f"Iniciando {current_name}..."))
    ray.get(status_actor.reset_progress.remote())

    try:
        # Validación previa con ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError("Archivo sin stream de vídeo válido")

        # Paso 1: Reparar (recodificación segura)
        print("Paso 1: reparar")
        repaired_path = video_path.rsplit('.', 1)[0] + "_repaired.mkv"
        ray.get(status_actor.set_progress.remote(0, 100))
        encoder = get_gpu_encoder()
        last_log_line = run_ffmpeg_with_progress([
            "ffmpeg", "-i", video_path,
            "-c:v", encoder, "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "384k",
            repaired_path
        ], status_actor)

        # Paso 2: Reducir
        print("Paso 2: reducir")
        ray.get(status_actor.set_step.remote(2))
        reduced_path = repaired_path.rsplit('.', 1)[0] + "_reduced.mkv"
        ray.get(status_actor.set_progress.remote(0, 100))
        last_log_line = run_ffmpeg_with_progress([
            "ffmpeg", "-i", repaired_path,
            "-vf", "scale=1280:720,format=yuv420p",
            "-c:v", encoder, "-preset", "fast", "-b:v", "2M",
            "-c:a", "aac", "-ac", "2",
            reduced_path
        ], status_actor)

        # Paso 3: Optimizar
        print("Paso 3: optimizar")
        ray.get(status_actor.set_step.remote(3))
        optimized_path = video_path.rsplit('.', 1)[0] + "-optimized.mkv"
        ray.get(status_actor.set_progress.remote(0, 100))
        last_log_line = run_ffmpeg_with_progress([
            "ffmpeg", "-i", reduced_path,
            "-vf", "scale=1280:720,format=yuv420p",
            "-c:v", encoder, "-preset", "fast",
            "-cq", "27", "-b:v", "800k", "-r", "30",
            "-c:a", "aac", "-ac", "2",
            "-movflags", "faststart", "-gpu", "0",
            optimized_path
        ], status_actor)
        
        # Paso 4: Convertir a MP4
        print("Paso 4: convertir a MP4")
        ray.get(status_actor.set_step.remote(4))
        mp4_path = video_path.rsplit('.', 1)[0] + "-final.mp4"
        ray.get(status_actor.set_progress.remote(0, 100))
        last_log_line = run_ffmpeg_with_progress([
            "ffmpeg", "-i", optimized_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            mp4_path
        ], status_actor)

        # Validación final
        print("Validación final")
        original_duration = get_video_duration(video_path)
        optimized_duration = get_video_duration(optimized_path)
        if abs(original_duration - optimized_duration) > 2:
            raise ValueError("La duración del archivo optimizado no coincide con el original")

        # Limpieza de temporales
        print("Limpieza de temporales")
        for path in [video_path, repaired_path, reduced_path]:
            try:
                os.remove(path)
            except Exception as e:
                logging.warning(f"No se pudo eliminar {path}: {e}")

        ray.get(status_actor.add_history.remote(current_name, "Procesado correctamente"))

    except subprocess.CalledProcessError as e:
        ray.get(status_actor.add_history.remote(current_name, f"Error de ffmpeg: {e.stderr.strip()}"))
    except ValueError as e:
        ray.get(status_actor.add_history.remote(current_name, f"Error de validación: {str(e)}"))
    except Exception as e:
        ray.get(status_actor.add_history.remote(current_name, f"Error inesperado: {str(e)}"))
        logging.exception("Error inesperado en process_pipeline")
    finally:
        ray.get(status_actor.set_video.remote(None))
        ray.get(status_actor.set_step.remote(0))
        ray.get(status_actor.reset_progress.remote())
        if not last_log_line or last_log_line == "Esperando progreso...":
            ray.get(status_actor.set_log_line.remote(last_log_line))

@ray.remote
def process_folder(path, status_actor):
    print(f"process_folder({path},{status_actor})")
    ray.get(status_actor.clear_history.remote())
    
    # Aceptar ruta de archivo individual
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        print(f"Estension: {ext}")
        if ext in valid_extensions:
            ray.get(status_actor.set_log_line.remote(f"Encolando archivo: {os.path.basename(path)}"))            
            process_pipeline.remote(path, status_actor)
        else:
            ray.get(status_actor.set_log_line.remote(f"Extensión no válida: {path}"))
        return

    # Si es carpeta, recorrer
    found_files = []
    for root, _, files in os.walk(path):
        for file in files:
            if os.path.splitext(file)[1].lower() in valid_extensions:
                found_files.append(os.path.join(root, file))

    if not found_files:
        msg = f"No se encontraron vídeos válidos en: {path}"
        print(msg)
        ray.get(status_actor.set_log_line.remote(msg))
        return

    print(f"🎯 Encontrados {len(found_files)} vídeos para procesar")
    for idx, video_path in enumerate(found_files, start=1):
        log_msg = f"[{idx}/{len(found_files)}] Encolando {os.path.basename(video_path)}"
        print(log_msg)
        ray.get(status_actor.set_log_line.remote(log_msg))
        process_pipeline.remote(video_path, status_actor)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    if not data or "folder" not in data:
        return jsonify({"error": "Ruta de archivo o carpeta no proporcionada"}), 400

    path = data["folder"]
    if not os.path.exists(path):
        return jsonify({"error": "La ruta especificada no existe"}), 400

    try:
        process_folder.remote(path, status_actor)
        return jsonify({"message": f"Procesamiento iniciado para: {path}"}), 200
    except Exception as e:
        return jsonify({"error": f"Error al procesar: {str(e)}"}), 500


@app.route("/process-file", methods=["POST"])
def process_file():
    if "video" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400

    video_file = request.files["video"]
    print(f"📥 Recibido archivo: {video_file.filename}")

    upload_folder = os.path.join(os.getcwd(), "uploads")
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, video_file.filename)
    video_file.save(save_path)
    print(f"💾 Guardado en: {save_path}")

    try:
        ray.get(status_actor.set_video.remote(video_file.filename, save_path))
        ray.get(status_actor.set_step.remote(1))
        ray.get(status_actor.reset_progress.remote())
        ray.get(status_actor.set_log_line.remote(f"Iniciando {video_file.filename}..."))

        process_pipeline.remote(save_path, status_actor)
        return jsonify({"message": f"Procesamiento iniciado para: {video_file.filename}"}), 200
    except Exception as e:
        print("❌ Error en process_file:", e)
        return jsonify({"error": f"Error al procesar: {str(e)}"}), 500

estado_actual = {}

def parse_ffmpeg_progress(line: str):
    global ultimo_resumen, estado_actual

    line = line.strip()
    print(f"{line}")

    # Detecta líneas clave tipo "key=value"
    if "=" in line:
        clave, valor = line.split("=", 1)
        estado_actual[clave.strip()] = valor.strip()

    # Si se detecta el final del proceso
    if line.startswith("progress=") and "end" in line:
        estado_actual.clear()
        ultimo_resumen = "completed"
        return "completed"

    # Genera resumen si hay todos los campos clave
    if all(k in estado_actual for k in ["frame", "fps", "out_time", "bitrate", "speed"]):
        resumen = (
            f" frames= {estado_actual['frame']} | fps= {estado_actual['fps']} | "
            f"time= {estado_actual['out_time']} | bitrate= {estado_actual['bitrate']} | "
            f"speed= {estado_actual['speed']}"
        )

        if resumen != ultimo_resumen:
            ultimo_resumen = resumen
            return resumen

    return None

def get_video_info(file_path):
    if not os.path.exists(file_path):
        return {}

    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(result.stdout)

        format_info = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

        return {
            "name": os.path.basename(file_path),
            "duration": f"{float(format_info.get('duration', 0)):.0f} sec",
            "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
            "format": format_info.get("format_name", "–"),
            "vcodec": video_stream.get("codec_name", "–"),
            "acodec": audio_stream.get("codec_name", "–"),
            "size": f"{int(format_info.get('size', 0)) / (1024**2):.1f} MB"
        }

    except Exception as e:
        print(f"Error al obtener info del vídeo: {e}")
        return {}

@app.route("/status", methods=["GET"])
def status():
    estado = ray.get(status_actor.get_status.remote())
    file_path = estado.get("current_file_path")
    estado["video_info"] = get_video_info(file_path) if file_path else {}
    return jsonify(estado)
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
