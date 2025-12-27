## video-optimezer — README

Breve: servidor Flask para optimizar vídeos (ffmpeg) con variantes CPU/GPU y una versión integrada con Ray para paralelizar tareas.

Contenido
- Descripción
- Requisitos
- Instalación rápida
- Cómo ejecutar (servidores y Ray)
- Endpoints HTTP y uso
- Solución de problemas

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

