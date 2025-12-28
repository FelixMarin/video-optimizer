# Docker Hub — felixmurcia/video-optimizer

Las imágenes oficiales de este proyecto están publicadas en Docker Hub:

https://hub.docker.com/repository/docker/felixmurcia/video-optimizer/general

Tags disponibles (ejemplos):
- `felixmurcia/video-optimizer:jetson` — build orientado a Jetson (ARM / L4T)
- `felixmurcia/video-optimizer:cuda` — build para hosts x86_64 con CUDA/NVIDIA
- `felixmurcia/video-optimizer:latest` — alias general (puede apuntar a `cuda`)

Nota: la imagen define por defecto el ENTRYPOINT:

```
["python3", "-m", "optimize_video"]
```

Por tanto, ejecutar el contenedor con opciones (`-h`, `-i`, etc.) invocará la CLI `optimize_video`.

Cómo descargar (pull):

```bash
docker pull felixmurcia/video-optimizer:jetson
docker pull felixmurcia/video-optimizer:cuda
```

Ejemplos de ejecución (pull -> run)

- Ejecutar la imagen Jetson (uso general, sin opción `--gpus` en x86):

```bash
docker run --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  felixmurcia/video-optimizer:jetson
```

- Ejecutar la imagen CUDA en host con NVIDIA Container Toolkit (exponer GPUs):

```bash
docker run --gpus all --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  felixmurcia/video-optimizer:cuda
```

- Ejecutar en Jetson con `--runtime nvidia` (si tu sistema lo requiere):

```bash
docker run --runtime nvidia --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  felixmurcia/video-optimizer:jetson
```

Ejecutar servidores específicos (sobrescribir `ENTRYPOINT`)

Como la imagen arranca por defecto la CLI `optimize_video`, para ejecutar los servidores hay que sobrescribir el `ENTRYPOINT` y llamar a `python3` con el script deseado. Ejemplos:

```bash
# Ejecutar server.py
docker run --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  --entrypoint python3 \
  felixmurcia/video-optimizer:cuda /app/server.py

# Ejecutar server-gpu.py (con GPUs)
docker run --gpus all --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  --entrypoint python3 \
  felixmurcia/video-optimizer:cuda /app/server-gpu.py

# Ejecutar server-gpu-ray.py (usa Ray si lo configuras)
docker run --gpus all --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  --entrypoint python3 \
  felixmurcia/video-optimizer:cuda /app/server-gpu-ray.py
```

Usar la CLI `optimize_video` incluida:

```bash
docker run --rm -v $(pwd)/inputs:/app/inputs -v $(pwd)/outputs:/app/outputs \
  felixmurcia/video-optimizer:cuda -h
```

O invocar el módulo Python directamente:

```bash
docker run --rm -v $(pwd)/inputs:/app/inputs -v $(pwd)/outputs:/app/outputs \
  --entrypoint python felixmurcia/video-optimizer:cuda -m optimize_video -h
```

Notas y recomendaciones:
- Monta las carpetas `uploads/` y `outputs/` para conservar los ficheros procesados en el host.
- En hosts x86_64 con GPU instala NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
- En Jetson asegúrate de usar la imagen compatible con tu versión de JetPack/L4T; para algunos pipelines puede ser necesario adaptar encoder (GStreamer/OMX en lugar de `h264_nvenc`).
- Si quieres que añada ejemplos en `docker-compose` o un script `start-server.sh` para elegir `server|server-gpu|server-gpu-ray` dentro de la imagen, dímelo y lo añado.
