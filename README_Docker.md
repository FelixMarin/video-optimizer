# Instrucciones Docker

Construye la imagen Docker desde la raíz del proyecto:

```bash
docker build -t video-optimezer:latest .
```

Ejecuta el contenedor para ver la ayuda del CLI (entrypoint ejecuta `python -m optimize_video`):

```bash
docker run --rm -it \
  -v "$PWD/inputs":/app/inputs \
  -v "$PWD/outputs":/app/outputs \
  video-optimezer:latest -h
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
- Si necesitas soporte GPU (cuentas con CUDA y librerías), avísame para preparar una variante basada en `nvidia/cuda`.
