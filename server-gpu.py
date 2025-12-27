from flask import Flask, request, jsonify, render_template
import os
import threading
import subprocess

app = Flask(__name__)

# Variables globales para el estado
current_video = None
current_step = 0
history = []

# Extensiones válidas de vídeo
valid_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"}

def process_video(video_path):
    global current_video, current_step, history

    # Ignorar archivos que ya tienen el sufijo "-optimized"
    if "-optimized" in video_path:
        return

    # Actualiza el estado del video en procesamiento
    current_video = os.path.basename(video_path)

    try:
        # Paso 1: Reparar archivo
        current_step = 1
        repaired_path = video_path.rsplit('.', 1)[0] + "_repaired.mkv"
        subprocess.run([
            "ffmpeg", 
            "-err_detect", "ignore_err",  # Ignora ciertos errores
            "-i", video_path,             # Archivo de entrada
            "-c", "copy",                 # Copia los streams sin codificar
            repaired_path                 # Archivo de salida
        ], check=True)

        # Paso 2: Reducir tamaño
        current_step = 2
        reduced_path = repaired_path.rsplit('.', 1)[0] + "_reduced.mkv"
        subprocess.run(
            [
                "ffmpeg", "-i", repaired_path, "-c:v", "h264_nvenc", "-preset", "fast",
                "-b:v", "2M", "-vf", "scale=1280:720", "-c:a", "aac", "-ac", "2", reduced_path
            ],
            check=True,
        )

        # Paso 3: Optimizar para streaming
        current_step = 3
        optimized_path = video_path.rsplit('.', 1)[0] + "-optimized.mkv"
        subprocess.run(
            [
                "ffmpeg", "-i", reduced_path,
                "-c:v", "h264_nvenc", "-preset", "fast",
                "-cq", "27", "-b:v", "800k", "-r", "30",
                "-vf", "scale=1280:720",
                "-c:a", "aac", "-ac", "2", "-movflags", "faststart",
                "-gpu", "0",  # Especifica la GPU a utilizar
                optimized_path
            ],
            check=True,
        )

        # Paso 4: Validar duración
        current_step = 4
        original_duration = get_video_duration(video_path)
        optimized_duration = get_video_duration(optimized_path)

        if abs(original_duration - optimized_duration) > 2:
            raise ValueError("La duración del archivo optimizado no coincide con el original")

        # Eliminar archivos intermedios y originales
        os.remove(video_path)
        os.remove(repaired_path)
        os.remove(reduced_path)

        # Si todo fue exitoso, actualiza el historial con éxito
        history.append({"name": current_video, "status": "Procesado correctamente"})
    except (subprocess.CalledProcessError, ValueError) as e:
        # Si ocurre un error, agrega el error al historial
        history.append({"name": current_video, "status": f"Error: {str(e)}"})
    finally:
        # Reinicia el video actual
        current_video = None
        current_step = 0

def get_video_duration(video_path):
    """Devuelve la duración del video en segundos."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except subprocess.CalledProcessError:
        return 0.0

def process_folder(folder_path):
    global history
    history = []  # Reinicia el historial

    for root, _, files in os.walk(folder_path):
        for file in files:
            if os.path.splitext(file)[1].lower() in valid_extensions:
                video_path = os.path.join(root, file)
                process_video(video_path)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    if not data or "folder" not in data:
        return jsonify({"error": "Ruta de carpeta no proporcionada"}), 400

    folder_path = data["folder"]
    if not os.path.exists(folder_path):
        return jsonify({"error": "La ruta especificada no existe"}), 400

    # Procesar carpeta en un hilo separado
    threading.Thread(target=process_folder, args=(folder_path,)).start()

    return jsonify({"message": f"Procesando carpeta: {folder_path}"}), 200

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "current_file": current_video,  # Cambiado para que coincida con el HTML
        "current_step": current_step,
        "history": history
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
