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

3) Ejecutar servidores (ejemplos)

- Servidor CPU (rápido, sin aceleración GPU):

```bash
python server.py
```

- Servidor con aceleración GPU (local):

```bash
python server-gpu.py
```

- Servidor con Ray (paralelización/distribución):

```bash
# En el nodo head (coordinador):
ray start --head --port=6379 --disable-usage-stats

# En los workers (o PCs remotos):
chmod +x start_ray_pc.sh
./start_ray_pc.sh   # editar la IP dentro del script si es necesario

# Luego iniciar la app que usa Ray:
python server-gpu-ray.py
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

5) Directorios relevantes
- `uploads/` — donde se guardan las subidas cuando se usa `/process-file`.
- `templates/` — contiene `index.html`, la UI simple.

6) Parámetros útiles y ajustes
- Si ajustas calidad/velocidad: modifica `crf`, `-b:v`, `-preset` o `-cq` en los scripts (`server*.py`).
- Para usar codificadores específicos en Jetson/PC revise `get_gpu_encoder()` en `server-gpu-ray.py`.

7) Troubleshooting rápido
- Asegúrate de que `ffmpeg`/`ffprobe` estén accesibles: `ffprobe -version` debe devolver algo.
- Si Ray no conecta: comprobar IP/puerto y firewalls, usar `ray status` en el head.
- Si ves errores de sesión Ray, limpiar `/tmp/ray` y `ray stop` en los nodos.

8) Despliegue sugerido (opciones)
- Systemd: crear un servicio que active el `venv` y lance `python server-gpu-ray.py`.
- Docker: crear una imagen con `ffmpeg` y Python; exportar puertos y montar `uploads/`.

9) Recursos y próximos pasos
- Ver [README.md](README.md) para una visión general del proyecto.
- Si quieres, puedo generar ejemplos de `systemd` unit file o un `Dockerfile`.
