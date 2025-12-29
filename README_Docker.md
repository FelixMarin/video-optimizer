# Instrucciones Docker

Construye la imagen Docker desde la raíz del proyecto:

```bash
docker build -t video-optimezer:latest .
```

Ejecuta el contenedor para ver la ayuda del CLI (entrypoint ejecuta `python optimize_video.py`):

```bash
docker run --rm -it \
  -v "$PWD/inputs":/app/inputs \
  -v "$PWD/outputs":/app/outputs \
  video-optimezer:latest python3 optimize_video.py -h
```

Ejemplo procesando un archivo dentro del contenedor (usa rutas en el contenedor `/app/inputs` y `/app/outputs`):

```bash
docker run --rm -it \
  -v "$PWD/inputs":/app/inputs \
  -v "$PWD/outputs":/app/outputs \
  video-optimezer:latest -i /app/inputs/el_cantico_final.mp4 -o /app/outputs
```

Con `docker-compose`:

```bash
docker-compose up --build
```

Notas:
- Asegúrate de tener `ffmpeg` y compiladores están instalados en la imagen (ya incluidos en el `Dockerfile`).

GPU / CUDA:
- Para entornos x86_64 con GPU NVIDIA usa la imagen `Dockerfile.cuda` incluida. Requiere que el host tenga instalado NVIDIA Container Toolkit (nvidia-docker). Ejemplo de build:

```bash
docker build -f Dockerfile.cuda -t video-optimezer:cuda .
docker run --gpus all --rm -it -v "$PWD/inputs":/app/inputs -v "$PWD/outputs":/app/outputs video-optimezer:cuda python3 optimize_video.py -i /app/inputs/el_cantico_final.mp4 -o /app/outputs
```

- Para NVIDIA Jetson (ARM aarch64) hay una plantilla `Dockerfile.jetson`. Adáptala a la versión de JetPack/L4T de la dispositivo y construye directamente en el Jetson o con herramientas cross-build:

```bash
# En Jetson
docker build -f Dockerfile.jetson -t video-optimezer:jetson .
```

Requisitos adicionales:
- En hosts x86_64 instala: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
- En Jetson normalmente no necesitas `nvidia-docker`, pero debes usar la imagen base compatible con la JetPack y tener los paquetes del sistema instalados.

Compatibilidad JetPack/L4T:

- La Jetson reporta: `R36 (REVISION: 4.7)` y CUDA `12.6`. Usa una imagen base L4T que coincida con R36.4.7 si vas a construir imágenes en el dispositivo. El `Dockerfile.jetson` en este repositorio apunta ahora a `nvcr.io/nvidia/l4t-base:r36.4.7`.
- Alternativa recomendada: construir y ejecutar localmente en la Jetson usando el Python del sistema (evita discrepancias entre la imagen y los controladores instalados). Ejemplo de ejecución directa (sin Docker):

```bash
python3 optimize_video.py -i /ruta/a/input.mp4 -o /ruta/a/outputs --backend gstreamer
```


Importante para Jetson (codificación):

- Las placas Jetson normalmente NO soportan `h264_nvenc`. En su lugar use pipelines de GStreamer/OMX (por ejemplo `omxh264enc`, `v4l2` o `nvmm`) para acceder al codificador hardware.
- El `Dockerfile.jetson` incluye `gstreamer1.0` y plugins; como ejemplo mínimo de pipeline para re-codificar un archivo usando el encoder hardware de Jetson:

```bash
gst-launch-1.0 filesrc location=/app/inputs/el_cantico_final.mp4 ! qtdemux name=demux \
  demux.video_0 ! queue ! decodebin ! nvvidconv ! 'video/x-raw(memory:NVMM),format=I420' ! omxh264enc ! h264parse ! qtmux ! filesink location=/app/outputs/out.mp4
```

- Ajusta el pipeline según la versión de JetPack/L4T y los plugins disponibles (`omxh264enc` vs `nvh264enc`, etc.). Si la aplicación invoca `ffmpeg` directamente, considera adaptar la invocación para usar GStreamer (`-f gstreamer`) o crear un wrapper que ejecute `gst-launch-1.0`.
