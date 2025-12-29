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

- **Archivo**: [optimize_video.py](optimize_video.py)
- **Requisitos**: `ffmpeg` y `ffprobe` disponibles en `PATH` (la herramienta invoca ambos).

**Comportamiento**: replica exactamente el pipeline de `server-gpu.py`:

- Paso 1 — Reparar: copia los streams con `-c copy` -> `*_repaired.mkv`.
- Paso 2 — Reducir: recodifica con `h264_nvenc`, `-b:v 2M`, escala `1280x720` -> `*_reduced.mkv`.
- Paso 3 — Optimizar para streaming: `-cq 27 -b:v 800k -r 30 -movflags faststart` -> `*-optimized.mkv` (usa `-gpu 0`).
- Paso 4 — Validar duración con `ffprobe`; si la diferencia es > 2s falla.
- Paso 5 — Si todo correcto, elimina el original y los intermedios.

**Uso**:

```bash
python3 optimize_video.py -i /ruta/al/video.mp4 -o /ruta/salida
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
python3 optimize_video.py -h
```

**Advertencias**:
- El proceso está pensado para máquinas con NVENC disponible; si `ffmpeg` no soporta `h264_nvenc` los pasos fallarán.
- El script borra el fichero original al finalizar correctamente: haz una copia si la necesitas.

### Ejemplos de uso

A continuación hay ejemplos prácticos usando el CLI (`optimize_video.py`).

- Optimización básica (usa valores por defecto):

```bash
python3 optimize_video.py -i /ruta/a/video.mp4 -o /ruta/salida
```

- Ajustar CQ (NVENC) y bitrate de optimización:

```bash
python3 optimize_video.py -i input.mkv -o outdir --cq 24 --opt-bitrate 1200k
```

- Cambiar bitrate en el paso de reducción y el CRF (si se usara libx264):

```bash
python3 optimize_video.py -i input.mov -o outdir --reduce-bitrate 3M --crf 20
```

- Seleccionar GPU diferente (p. ej. GPU 1):

```bash
python3 optimize_video.py -i input.mp4 -o outdir --gpu 1
```

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