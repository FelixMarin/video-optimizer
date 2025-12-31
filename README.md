## video-optimezer — README

Breve: servidor Flask para optimizar vídeos (ffmpeg) con variantes CPU/GPU y una versión integrada con Ray para paralelizar tareas.

Contenido
- Descripción
- Requisitos
- Instalación rápida
- Cómo ejecutar (servidores y Ray)
- Endpoints HTTP y uso
- Solución de problemas
 - Docker (build / push / pull / uso) — ver DOCKER.md

Descripción
El proyecto expone una interfaz web (plantilla en `templates/index.html`) y endpoints API para encolar y procesar vídeos desde una carpeta o subida de archivo. Hay tres variantes principales:

- `server.py`: pipeline simple (CPU, sin aceleración GPU).
- `server-gpu.py`: utiliza codificadores GPU (p. ej. `h264_nvenc` / `h264_nvmpi`).
- `server-gpu-ray.py`: misma lógica pero delega trabajo a Ray (actor `StatusTracker` y tareas remotas) para ejecución distribuida/asincrónica.

Requisitos
- Python 3.10+ recomendado
- ffmpeg y ffprobe en PATH
- Ray (si usa la versión `*-ray.py`)
- Dependencias listadas en `requirements.txt`

Instalación rápida
1. Crear y activar un virtualenv (ejemplo):

```bash
python -m venv venv
source venv/bin/activate
```

2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Asegurar `ffmpeg` y `ffprobe` instalados (apt, yum, o binarios).

Ray (opcional)
- Instalar Ray si usas `server-gpu-ray.py`:

```bash
pip install "ray[default]==2.42.1"
```

Uso: Ray (nodo head / worker)
- Iniciar nodo head (por ejemplo, en Jetson / máquina que hará de coordinador):

```bash
ray start --head --port=6379 --disable-usage-stats
```

- Iniciar worker (PC) — hay un script de ejemplo `start_ray_pc.sh` en el repo. Para usarlo:

```bash
chmod +x start_ray_pc.sh
./start_ray_pc.sh
```

Nota: `start_ray_pc.sh` usa la dirección `192.168.0.105:6379` por defecto; edítalo si tu `head` está en otra IP.

Ejecutar el servidor Flask
- Versión simple (CPU):

```bash
python server.py
```

- Versión GPU local:

```bash
python server-gpu.py
```

- Versión con Ray (recomendado para procesamiento paralelo/distribuido):

```bash
python server-gpu-ray.py
```

API / Endpoints
- `GET /` — interfaz web (usa `templates/index.html`).
- `POST /process` — JSON: `{ "folder": "/ruta/a/carpeta" }` para encolar carpeta o archivo.
- `POST /process-file` — multipart/form-data con campo `video` para subir y procesar un solo archivo (implementado en `server-gpu-ray.py`).
- `GET /status` — devuelve estado actual, progreso y `video_info` (en `server-gpu-ray.py` devuelve info extra con `ffprobe`).

Carpetas importantes
- `uploads/` — destino por defecto para archivos subidos.
- `templates/` — plantilla web `index.html`.

Solución de problemas
- Si Ray no se conecta: verifica que la IP y puerto del `head` sean accesibles desde los workers (firewall/puertos).
- Comprobar estado del cluster en el head:

```bash
ray status
```

- Para limpiar sesiones de Ray (si hay errores de sesión):

```bash
sudo rm -rf /tmp/ray
ray stop
```

- Si `ffmpeg` falla: prueba comandos manualmente y revisa que `ffprobe` devuelva streams válidos.

Notas finales
- Ajusta parámetros de `ffmpeg` (CRF, bitrate, preset) según calidad/velocidad deseada.
- Revisa `server-gpu-ray.py` para entender el actor `StatusTracker` y cómo se parsea la salida de `ffmpeg` para progreso en tiempo real.

Archivo con dependencias: `requirements.txt`

[Modo de uso](https://github.com/FelixMarin/video-optimizer/blob/master/USAGE.md)


## CLI: optimizar vídeo desde la línea de comandos

Se añadió un módulo mínimo para ejecutar la optimización sin levantar el servidor ni Ray.

- **Archivo**: [optimize_video/__main__.py](optimize_video/__main__.py)
- **Requisitos**: `ffmpeg` y `ffprobe` disponibles en `PATH` (la herramienta invoca ambos).

**Comportamiento**: replica exactamente el pipeline de `server-gpu.py`:

- Paso 1 — Reparar: copia los streams con `-c copy` -> `*_repaired.mkv`.
- Paso 2 — Reducir: recodifica con `h264_nvenc`, `-b:v 2M`, escala `1280x720` -> `*_reduced.mkv`.
- Paso 3 — Optimizar para streaming: `-cq 27 -b:v 800k -r 30 -movflags faststart` -> `*-optimized.mkv` (usa `-gpu 0`).
- Paso 4 — Validar duración con `ffprobe`; si la diferencia es > 2s falla.
- Paso 5 — Si todo correcto, elimina el original y los intermedios.

**Uso**:

```bash
python -m optimize_video -i /ruta/al/video.mp4 -o /ruta/salida
```

- `-i/--input`: fichero de entrada (`.mp4`, `.mkv`, `.avi`, `.mov`, `.flv`, `.wmv`).
- `-o/--output`: carpeta donde se crean los intermedios y el resultado final.

**Salida**: el fichero final se guarda como `<basename>-optimized.mkv` dentro de la carpeta `-o`.

**Códigos de salida**:
- `0` — éxito
- `1` — error en el procesamiento
- `2` — fichero de entrada no encontrado o extensión inválida

**Ayuda**:

```bash
python -m optimize_video -h
```

**Advertencias**:
- El proceso está pensado para máquinas con NVENC disponible; si `ffmpeg` no soporta `h264_nvenc` los pasos fallarán.
- El script borra el fichero original al finalizar correctamente: haz una copia si la necesitas.

### Ejemplos de uso

A continuación hay ejemplos prácticos usando el módulo CLI ([optimize_video/__main__.py](optimize_video/__main__.py)).

- Optimización básica (usa valores por defecto):

```bash
python -m optimize_video -i /ruta/a/video.mp4 -o /ruta/salida
```

- Ajustar CQ (NVENC) y bitrate de optimización:

```bash
python -m optimize_video -i input.mkv -o outdir --cq 24 --opt-bitrate 1200k
```

- Cambiar bitrate en el paso de reducción y el CRF (si se usara libx264):

```bash
python -m optimize_video -i input.mov -o outdir --reduce-bitrate 3M --crf 20
```

- Seleccionar GPU diferente (p. ej. GPU 1):

```bash
python -m optimize_video -i input.mp4 -o outdir --gpu 1
```
# USAGE — video-optimezer

Este archivo resume los pasos mínimos para instalar, ejecutar y usar el servicio de optimización de vídeo incluido en este repositorio.

1) Requisitos
- Python 3.10+
- `ffmpeg` y `ffprobe` disponibles en `PATH`
- (Opcional) Ray si usas la variante `server-gpu-ray.py`

2) Preparación rápida

```bash
git clone <repo>    # si aplica
cd video-optimezer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Instalar Ray (opcional):

```bash
pip install "ray[default]==2.42.1"
```

4) API - ejemplos prácticos

- Encolar carpeta para procesar (JSON):

```bash
curl -X POST http://localhost:5000/process \
  -H 'Content-Type: application/json' \
  -d '{"folder": "/ruta/a/carpeta_con_videos"}'
```

- Subir y procesar un solo archivo (multipart/form-data):

```bash
curl -X POST http://localhost:5000/process-file \
  -F "video=@/ruta/al/video.mp4"
```

- Consultar estado y progreso:

```bash
curl http://localhost:5000/status
```

3) Directorios relevantes
- `uploads/` — donde se guardan las subidas cuando se usa `/process-file`.
- `templates/` — contiene `index.html`, la UI simple.

4) Parámetros útiles y ajustes
- Si ajustas calidad/velocidad: modifica `crf`, `-b:v`, `-preset` o `-cq` en los scripts (`server*.py`).
- Para usar codificadores específicos en Jetson/PC revise `get_gpu_encoder()` en `server-gpu-ray.py`.

5) Troubleshooting rápido
- Asegúrate de que `ffmpeg`/`ffprobe` estén accesibles: `ffprobe -version` debe devolver algo.
- Si Ray no conecta: comprobar IP/puerto y firewalls, usar `ray status` en el head.
- Si ves errores de sesión Ray, limpiar `/tmp/ray` y `ray stop` en los nodos.

6) Despliegue sugerido (opciones)
- Systemd: crear un servicio que active el `venv` y lance `python server-gpu-ray.py`.
- Docker: crear una imagen con `ffmpeg` y Python; exportar puertos y montar `uploads/`.

7) Recursos y próximos pasos
- Ver [README.md](README.md) para una visión general del proyecto.
- Si quieres, puedo generar ejemplos de `systemd` unit file o un `Dockerfile`.


# Video Optimizer - Comandos de Ejecución

## 📦 INSTALACIÓN LOCAL

# Crear entorno virtual
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

## 🚀 COMANDOS CLI

# Optimizar video básico
python -m optimize_video -i inputs/el_cantico_final.mp4 -o ./outputs
python -m optimize_video -i inputs/Projetc_2.mp4 -o ./outputs

# Con GStreamer en Jetson
python -m optimize_video -i inputs/el_cantico_final.mp4 -o outputs --backend gstreamer

## 🌐 SERVIDORES WEB

# Servidor básico
python -m server

# Servidor con GPU
python -m server-gpu

# Servidor con Ray
python -m server-gpu-ray

# Servidor Jetson
python -m server-gpu-jetson

# Por defecto en: http://localhost:5000

## 🐳 DOCKER - CONSTRUCCIÓN

# Imagen base
docker build -t video-optimezer:latest .

# Imagen CUDA
docker build --no-cache -f Dockerfile.cuda -t video-optimezer:cuda .

# Imagen Jetson
docker build -f Dockerfile.jetson -t video-optimizer:jetson .

## 🐳 DOCKER - EJECUCIÓN

# Mostrar ayuda
docker run --rm -it -v "$PWD/inputs":/app/inputs -v "$PWD/outputs":/app/outputs video-optimezer:latest -h

# Optimizar video
docker run --rm -it -v "$PWD/inputs":/app/inputs -v "$PWD/outputs":/app/outputs video-optimezer:latest -i /app/inputs/el_cantico_final.mp4 -o /app/outputs

# Con CUDA (GPU)
docker run --rm -it --gpus all -v "$PWD/inputs":/app/inputs -v "$PWD/outputs":/app/outputs video-optimezer:cuda -i /app/inputs/el_cantico_final.mp4 -o /app/outputs

## 🐳 DOCKER - TAGGING Y PUSH

# Tagging para Docker Hub
docker tag video-optimezer:latest felixmurcia/video-optimezer:latest
docker tag video-optimizer:jetson felixmurcia/video-optimizer:jetson
docker tag video-optimizer:latest felixmurcia/video-optimizer:cuda

# Subir a Docker Hub
docker push felixmurcia/video-optimezer:latest
docker push felixmurcia/video-optimizer:jetson
docker push felixmurcia/video-optimizer:cuda

# Descargar
docker pull felixmurcia/video-optimizer:cuda
docker pull felixmurcia/video-optimizer:jetson

## 🔧 PRUEBAS JETSON

# Pipeline GStreamer de prueba
gst-launch-1.0 filesrc location=input.mp4 ! qtdemux ! h264parse ! nvv4l2h264enc ! qtmux ! filesink location=output.mp4

# Script específico Jetson
./run-jetson.sh ./inputs/el_cantico_final.mp4 ./outputs

## 📁 ESTRUCTURA BÁSICA

optimize_video.py      # CLI principal
server.py              # Servidor básico
server-gpu.py          # Servidor con GPU
server-gpu-ray.py      # Servidor distribuido
server-gpu-jetson.py   # Servidor Jetson (GStreamer)
requirements.txt       # Dependencias Python
Dockerfile            # Imagen base
Dockerfile.cuda       # Imagen CUDA
Dockerfile.jetson     # Imagen Jetson
run-jetson.sh         # Script para Jetson
run_video_optimizer.bat # Script Windows

## ⚙️ OPCIONES CLI PRINCIPALES

-i, --input         Archivo de video entrada (requerido)
-o, --output        Directorio salida (requerido)
--backend          Motor: auto/ffmpeg/gstreamer
--reduce-bitrate   Bitrate reducción (ej: 2M)
--opt-bitrate      Bitrate optimización (ej: 800k)
--server           Ejecutar servidor web

## 📋 BACKENDS DISPONIBLES

auto       - Automático (GStreamer en Jetson, FFmpeg en otros)
ffmpeg     - FFmpeg puro (CPU)
gstreamer  - GStreamer (HW decode + SW encode)

## 🖥️ PUERTOS SERVIDORES

server              : Puerto 5000
server-gpu          : Puerto 5000  
server-gpu-ray      : Puerto 5000
server-gpu-jetson   : Puerto 5001

## 📝 EJEMPLOS COMPLETOS

# 1. CLI básico
python -m optimize_video -i inputs/video.mp4 -o outputs/ --reduce-bitrate 2M --opt-bitrate 800k

# 2. Docker producción
docker run --rm -d \
  -v /data/inputs:/app/inputs \
  -v /data/outputs:/app/outputs \
  -p 5000:5000 \
  video-optimizer:latest \
  --server server-gpu

# 3. Jetson local
./run-jetson.sh ./inputs/mi_video.mp4 ./outputs

# 4. Batch Windows
run_video_optimizer.bat el_cantico_final.mp4 C:\Users\usuario\outputs

Notas:
- `--cq` controla la calidad para NVENC en el paso de optimización (valor más bajo = mejor calidad).
- `--reduce-bitrate` y `--opt-bitrate` aceptan valores tipo `800k`, `2M`, `3M`, etc.
- El parámetro `--crf` está disponible para escenarios donde se use `libx264` como alternativa; si su `ffmpeg` no soporta `h264_nvenc` el pipeline puede fallar según la configuración del sistema.

## Ventana principal
![index.html](https://raw.githubusercontent.com/FelixMarin/video-optimizer/refs/heads/master/images/index.png)

## Ejecución
![Ejecución](https://raw.githubusercontent.com/FelixMarin/video-optimizer/refs/heads/master/images/ejecucion.png)

## Log del proceso
![Logs del proceso](https://raw.githubusercontent.com/FelixMarin/video-optimizer/refs/heads/master/images/ejecucion2.png)
